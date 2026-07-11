"""IronFlock companion process for wg-easy.

Started in the background by entrypoint.sh and owns all platform integration:

1. Publishes this device's web UI url to the IronFlock `devices` table once the
   WAMP connection joins the router (feeds the dashboard embed defined in
   .ironflock/board-template.yml).
2. Keeps the client-facing VPN endpoint (the "Endpoint = host:port" line in
   downloaded client configs) in sync with the tunnel. wg-easy stores host/port
   in user_configs_table and reads them from SQLite on EVERY config download, but
   only applies INIT_* on the very first boot — while the device agent
   activates/deactivates tunnels and rewrites the /data/env/*.txt files in
   RUNNING containers without a restart. The sync loop therefore polls the
   SDK-computed endpoint and rewrites the DB row whenever it changes.
3. Re-applies the "Allowed IPs clients will use" parameter (INIT_ALLOWED_IPS)
   when its value changes: wg-easy honours INIT_* only on the very first boot,
   but the app parameters are the natural config surface on IronFlock. Only
   the default for newly created clients is updated (sync_allowed_ips_once).

The endpoint sync deliberately does NOT depend on the WAMP connection — it must
keep working when the router is unreachable (e.g. restrictive corporate
networks where only the tunnel itself gets out).
"""

import asyncio
import json
import os
import sqlite3
from datetime import datetime
from urllib.parse import urlsplit

from ironflock import IronFlock

ironflock: IronFlock  # assigned in __main__; used by the functions below after assignment

# Physical location of wg-easy's DB: the server opens /etc/wireguard/wg-easy.db,
# which entrypoint.sh symlinks onto the persistent /data volume.
DB_PATH = "/data/wg-easy.db"
WEB_UI_PORT = 51821  # must match port-template.yml
VPN_PORT = 51820  # must match port-template.yml (the wg ListenPort — enforced in the DB)
SYNC_INTERVAL_SECONDS = 10  # the agent updates /data/env within seconds of a tunnel toggle
# Last INIT_ALLOWED_IPS value this app applied to the DB (see sync_allowed_ips_once)
ALLOWED_IPS_STATE = "/data/.ironflock_applied_allowed_ips"


def get_vpn_endpoint():
    """Current public VPN endpoint as (host, port), or None while the tunnel is inactive.

    The SDK composes it from the device identity, TUNNEL_DOMAIN and the
    tunnel-assigned public UDP port (WG_PORT / WG_PORT_CLOUD on instance
    devices), reading the live agent-maintained files under /data/env.
    """
    url = ironflock.getRemoteAccessUrlForPort(
        VPN_PORT, protocol="udp", remote_port_environment="WG_PORT"
    )
    if not url:
        return None
    parts = urlsplit(url)
    if not (parts.hostname and parts.port):
        return None
    return parts.hostname, parts.port


def sync_endpoint_once():
    """Keep wg-easy's stored endpoint in line with the tunnel's current one.

    This takes ownership of the interface Host/Port — do not edit them in the
    Admin UI for this app. user_configs_table.host/port (the advertised client
    endpoint) follow the tunnel, and interfaces_table.port (the wg ListenPort)
    is enforced back to 51820 because the tunnel always forwards the public
    port there. Writes are single short UPDATEs: wg-easy's own connection runs
    with busy_timeout=0, so holding locks longer would make its requests fail.
    """
    if not os.path.exists(DB_PATH):
        return  # first boot — wg-easy has not created its database yet
    endpoint = get_vpn_endpoint()  # None while the tunnel is inactive
    # mode=rw so a race on the check above can never create an empty DB file
    con = sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True, timeout=5)
    try:
        setup = con.execute("SELECT setup_step FROM general_table").fetchone()
        if setup is None or setup[0] != 0:
            return  # first-boot setup still running (setup_step != 0) — don't race its writes
        # Repair installs whose first boot seeded the public tunnel port as the wg
        # ListenPort (an older entrypoint passed WG_PORT as INIT_PORT, and wg-easy's
        # setup writes INIT_PORT into interfaces_table.port too). wg re-reads it on
        # the next container restart; the DB must be fixed for that restart to heal.
        cur = con.execute(
            "UPDATE interfaces_table SET port = ? WHERE port != ?", (VPN_PORT, VPN_PORT)
        )
        if cur.rowcount:
            con.commit()
            print(f"endpoint sync: repaired wg ListenPort to {VPN_PORT} (applies on next restart)")
        if endpoint is None:
            return  # tunnel inactive — keep the last known advertised endpoint
        host, port = endpoint
        row = con.execute("SELECT host, port FROM user_configs_table").fetchone()
        if row is None:
            return  # schema exists but the config row is not seeded yet
        if (row[0], row[1]) == (host, port):
            return
        con.execute("UPDATE user_configs_table SET host = ?, port = ?", (host, port))
        con.commit()
        print(f"endpoint sync: client Endpoint set to {host}:{port} (was {row[0]}:{row[1]})")
    finally:
        con.close()


def sync_allowed_ips_once():
    """Apply an INIT_ALLOWED_IPS parameter *change* to the default Allowed IPs.

    wg-easy honours INIT_* only on the very first boot, but for IronFlock users
    the app parameters are the natural config surface. Semantics: last writer
    wins — the parameter is (re)applied only when it differs from the value
    recorded as last applied (state file on /data), so Web UI edits persist
    until the parameter is changed again. This updates only the DEFAULT used
    for newly created clients; existing clients keep their own copy (wg-easy
    copies the default into each client at creation) and are edited/recreated
    in the Web UI.

    Returns True once handled (applied, or nothing to do) so the caller can
    stop retrying for this container run; False while the DB is not ready.
    """
    param = os.environ.get("INIT_ALLOWED_IPS", "")
    wanted = [x.strip() for x in param.split(",") if x.strip()]
    if not wanted:
        return True  # parameter unset/empty — nothing to manage
    try:
        with open(ALLOWED_IPS_STATE) as f:
            last_applied = f.read().strip()
    except OSError:
        last_applied = None
    if last_applied == param:
        return True  # unchanged since last applied — the Web UI owns the value
    if not os.path.exists(DB_PATH):
        return False  # first boot — wg-easy applies INIT_ALLOWED_IPS itself there
    con = sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True, timeout=5)
    try:
        setup = con.execute("SELECT setup_step FROM general_table").fetchone()
        if setup is None or setup[0] != 0:
            return False  # first-boot setup still running — don't race its writes
        # stored as a JSON string array, e.g. '["0.0.0.0/0","::/0"]'
        wanted_json = json.dumps(wanted, separators=(",", ":"))
        cur = con.execute(
            "UPDATE user_configs_table SET default_allowed_ips = ? WHERE default_allowed_ips != ?",
            (wanted_json, wanted_json),
        )
        con.commit()
        if cur.rowcount:
            print(
                f"allowed-ips sync: default Allowed IPs set to {', '.join(wanted)} "
                "(affects newly created clients; existing clients keep their own value)"
            )
    finally:
        con.close()
    with open(ALLOWED_IPS_STATE, "w") as f:
        f.write(param)
    return True


async def endpoint_sync_loop():
    print(
        f"endpoint sync: keeping {DB_PATH} in sync with the tunnel endpoint "
        f"(checking every {SYNC_INTERVAL_SECONDS}s)"
    )
    allowed_ips_done = False
    while True:
        try:
            await asyncio.to_thread(sync_endpoint_once)
            if not allowed_ips_done:
                allowed_ips_done = await asyncio.to_thread(sync_allowed_ips_once)
        except Exception as exc:  # locked DB, missing table, ... — retry next tick
            print(f"endpoint sync: skipped ({exc})")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


async def register_device():
    # runs once after the connection joins the router
    print("########### Storing Device info ################")
    url = ironflock.getRemoteAccessUrlForPort(WEB_UI_PORT)
    if not url:
        print("WARNING: could not compose the web UI url (device identity env missing?) — not publishing")
        return
    await ironflock.append_to_table(
        "devices",
        {
            "tsp": datetime.now().astimezone().isoformat(),
            "url": url,
            "state": 1,
        },
    )
    print("done")
    # returning lets run_async() close the WAMP connection cleanly — the sync loop lives on


async def run_wamp():
    try:
        await ironflock.run_async()
    except Exception as exc:
        print(f"device registration: router connection failed ({exc}) — endpoint sync continues")


async def main():
    wamp_task = asyncio.create_task(run_wamp())
    try:
        await endpoint_sync_loop()  # runs forever
    finally:
        wamp_task.cancel()


if __name__ == "__main__":
    ironflock = IronFlock(mainFunc=register_device)
    asyncio.run(main())
