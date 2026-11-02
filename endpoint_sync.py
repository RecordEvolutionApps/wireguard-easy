"""Keep wg-easy's database in step with the IronFlock tunnel and the parameters.

wg-easy applies its INIT_* variables only on the very first boot, but on
IronFlock two things change afterwards without a container restart:

1. The public VPN endpoint. The device agent activates and deactivates the
   UDP tunnel and rewrites /data/env/*.txt in the RUNNING container; the SDK
   reads those files live. `sync_endpoint_once` copies the current endpoint
   into user_configs_table.host/port, which wg-easy re-reads on every config
   download and QR code, and enforces interfaces_table.port = 51820, the port
   the tunnel forwards to (effective on the next restart).
2. The "Allowed IPs clients will use" parameter. `sync_allowed_ips_once`
   re-applies it to the default for new clients when it differs from the
   value last applied (state file on /data): last writer wins, so Web UI
   edits persist until the parameter changes again.

Both functions are plain, synchronous, and need no platform connection. They
return the events they caused as dicts {level, kind, message, detail} so the
caller can log them to the events table.

wg-easy's own SQLite connection runs with journal mode `delete` and
busy_timeout=0, so writes here are single short UPDATEs, and nothing is
written while the first-boot setup runs (general_table.setup_step != 0).
"""

import json
import os
import sqlite3
from urllib.parse import urlsplit

from vpn_state import DB_PATH, VPN_PORT, WEB_UI_PORT

ALLOWED_IPS_STATE = "/data/.ironflock_applied_allowed_ips"
DEV_LABEL_SUFFIX = "-dev"


def event(level, kind, message, **detail):
    return {"level": level, "kind": kind, "message": message, "detail": detail}


def get_vpn_endpoint(flock) -> tuple[str, int] | None:
    """Current public VPN endpoint as (host, port), or None while the tunnel
    is inactive. Composed by the SDK from the device identity, TUNNEL_DOMAIN
    and the tunnel-assigned public UDP port (WG_PORT, or WG_PORT_CLOUD on
    appliance devices), read live from /data/env."""
    url = flock.getRemoteAccessUrlForPort(VPN_PORT, protocol="udp", remote_port_environment="WG_PORT")
    if not url:
        return None
    parts = urlsplit(url)
    if not (parts.hostname and parts.port):
        return None
    return parts.hostname, parts.port


def get_web_ui_url(flock) -> str | None:
    """HTTPS tunnel URL of the wg-easy Web UI, for this run's stage.

    Development runs are tunnelled under the production label with a `-dev`
    suffix (`4749-wireguard_easy-51821-dev.app.ironflock.com`), but the SDKs
    (ironflock-py 1.11.0, ironflock-js 1.10.0) compose the label without a
    stage, so in a DEV container they return the production install's URL.
    Until they do it themselves, the suffix is added here to the SDK's own
    URL; the routing is otherwise left to the SDK. A label that already ends
    in `-dev` is kept, so this becomes a no-op once the SDK is fixed.
    """
    url = flock.getRemoteAccessUrlForPort(WEB_UI_PORT)
    # Same stage rule as the SDK (_stage_from_env): only PROD is production.
    if not url or os.environ.get("ENV", "").upper() == "PROD":
        return url
    parts = urlsplit(url)
    label, dot, domain = (parts.hostname or "").partition(".")
    if not dot or label.endswith(DEV_LABEL_SUFFIX):
        return url
    label += DEV_LABEL_SUFFIX
    if len(label) > 63:  # not a valid DNS label: the platform cannot serve it
        return None
    return parts._replace(netloc=f"{label}.{domain}").geturl()


def _connect_rw():
    # mode=rw: never create an empty database file by accident
    return sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True, timeout=5)


def _setup_done(con) -> bool:
    row = con.execute("SELECT setup_step FROM general_table").fetchone()
    return row is not None and row[0] == 0


def sync_endpoint_once(endpoint: tuple[str, int] | None) -> list[dict]:
    """Write the tunnel's endpoint into wg-easy's advertised Host/Port.

    This owns the interface Host and Port: do not edit them in the Admin
    Panel for this app, they are overwritten within seconds.
    """
    events: list[dict] = []
    if not os.path.exists(DB_PATH):
        return events  # first boot: wg-easy has not created its database yet
    con = _connect_rw()
    try:
        if not _setup_done(con):
            return events  # setup still running: don't race its writes
        cur = con.execute("UPDATE interfaces_table SET port = ? WHERE port != ?", (VPN_PORT, VPN_PORT))
        if cur.rowcount:
            con.commit()
            events.append(
                event(
                    "warning",
                    "listen_port_repaired",
                    f"wg ListenPort reset to {VPN_PORT}; applies on the next restart of the app",
                    port=VPN_PORT,
                )
            )
        if endpoint is None:
            return events  # tunnel inactive: keep the last known advertised endpoint
        host, port = endpoint
        row = con.execute("SELECT host, port FROM user_configs_table").fetchone()
        if row is None or (row[0], row[1]) == (host, port):
            return events
        con.execute("UPDATE user_configs_table SET host = ?, port = ?", (host, port))
        con.commit()
        events.append(
            event(
                "info",
                "endpoint_changed",
                f"client Endpoint set to {host}:{port} (was {row[0]}:{row[1]}); re-download client configs",
                host=host,
                port=port,
                previous=f"{row[0]}:{row[1]}",
            )
        )
        return events
    finally:
        con.close()


def sync_allowed_ips_once() -> tuple[bool, list[dict]]:
    """Apply a changed INIT_ALLOWED_IPS parameter to the default Allowed IPs.

    Returns (done, events). `done` is True once handled for this container
    run (applied, or nothing to do) and False while the DB is not ready.
    Only the default for NEW clients changes; existing clients keep their own
    copy (wg-easy copies the default into each client at creation).
    """
    param = os.environ.get("INIT_ALLOWED_IPS", "")
    wanted = [x.strip() for x in param.split(",") if x.strip()]
    if not wanted:
        return True, []
    try:
        with open(ALLOWED_IPS_STATE) as f:
            last_applied = f.read().strip()
    except OSError:
        last_applied = None
    if last_applied == param:
        return True, []
    if not os.path.exists(DB_PATH):
        return False, []  # first boot: wg-easy applies INIT_ALLOWED_IPS itself
    events: list[dict] = []
    con = _connect_rw()
    try:
        if not _setup_done(con):
            return False, []
        wanted_json = json.dumps(wanted, separators=(",", ":"))  # stored as a JSON string array
        cur = con.execute(
            "UPDATE user_configs_table SET default_allowed_ips = ? WHERE default_allowed_ips != ?",
            (wanted_json, wanted_json),
        )
        con.commit()
        if cur.rowcount:
            events.append(
                event(
                    "info",
                    "allowed_ips_applied",
                    f"default Allowed IPs for new clients set to {', '.join(wanted)} from the app parameter",
                    allowed_ips=wanted,
                )
            )
    finally:
        con.close()
    with open(ALLOWED_IPS_STATE, "w") as f:
        f.write(param)
    return True, events
