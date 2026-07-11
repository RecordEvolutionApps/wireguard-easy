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

The endpoint sync deliberately does NOT depend on the WAMP connection — it must
keep working when the router is unreachable (e.g. restrictive corporate
networks where only the tunnel itself gets out).
"""

import asyncio
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
VPN_PORT = 51820  # must match port-template.yml (the internal ListenPort — never rewritten)
SYNC_INTERVAL_SECONDS = 10  # the agent updates /data/env within seconds of a tunnel toggle


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
    """Rewrite wg-easy's stored endpoint if it differs from the tunnel's current one.

    This takes ownership of the interface Host/Port — do not edit them in the
    Admin UI for this app. Only user_configs_table.host/port are touched (the
    advertised endpoint); interfaces_table.port (the wg ListenPort) stays 51820.
    The write is a single short UPDATE: wg-easy's own connection runs with
    busy_timeout=0, so holding locks longer would make its requests fail.
    """
    endpoint = get_vpn_endpoint()
    if endpoint is None:
        return  # tunnel inactive — keep the last known endpoint
    host, port = endpoint
    if not os.path.exists(DB_PATH):
        return  # first boot — wg-easy has not created its database yet
    # mode=rw so a race on the check above can never create an empty DB file
    con = sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True, timeout=5)
    try:
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


async def endpoint_sync_loop():
    print(
        f"endpoint sync: keeping {DB_PATH} in sync with the tunnel endpoint "
        f"(checking every {SYNC_INTERVAL_SECONDS}s)"
    )
    while True:
        try:
            await asyncio.to_thread(sync_endpoint_once)
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
