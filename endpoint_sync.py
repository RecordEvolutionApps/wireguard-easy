"""Keep wg-easy's database in step with the IronFlock tunnel and the board.

wg-easy applies its INIT_* variables only on the very first boot, but on
IronFlock two things change afterwards without a container restart:

1. The public VPN endpoint. The device agent activates and deactivates the
   UDP tunnel and rewrites /data/env/*.txt in the RUNNING container; the SDK
   reads those files live. `sync_endpoint_once` copies the current endpoint
   into user_configs_table.host/port, which wg-easy re-reads on every config
   download and QR code, and enforces interfaces_table.port = 51820, the port
   the tunnel forwards to (effective on the next restart).
2. The default Allowed IPs for new clients, which users set on the board
   (table gateway_settings). `apply_default_allowed_ips` writes it into
   user_configs_table.default_allowed_ips; the caller decides which settings
   row is in force (register_device.py).

The functions are plain, synchronous, and need no platform connection
(settings rows reach the caller only while it is connected, though). They
return the events they caused as dicts {level, kind, message, detail} so the
caller can log them to the events table.

wg-easy's own SQLite connection runs with journal mode `delete` and
busy_timeout=0, so writes here are single short UPDATEs, and nothing is
written while the first-boot setup runs (general_table.setup_step != 0).
"""

import ipaddress
import json
import os
import sqlite3
from urllib.parse import urlsplit

from vpn_state import DB_PATH, VPN_PORT, WEB_UI_PORT


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
    """HTTPS tunnel URL of the wg-easy Web UI. A development run gets its own
    tunnel, whose label ends in -dev; the SDK (ironflock 1.11.2 and later)
    returns that one itself."""
    return flock.getRemoteAccessUrlForPort(WEB_UI_PORT)


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


def parse_allowed_ips(value) -> list[str]:
    """Split and validate a comma-separated Allowed IPs value from the board.

    Raises ValueError naming the first entry that is not an IP network."""
    entries = [x.strip() for x in str(value or "").split(",") if x.strip()]
    if not entries:
        raise ValueError("no Allowed IPs given")
    for entry in entries:
        try:
            ipaddress.ip_network(entry, strict=False)
        except ValueError:
            raise ValueError(f"'{entry}' is not an IP address or network in CIDR notation") from None
    return entries


def apply_default_allowed_ips(allowed: list[str]) -> tuple[bool, list[dict]]:
    """Write the default Allowed IPs for NEW clients into wg-easy.

    Returns (done, events). `done` is False while wg-easy's database is not
    ready (first boot, setup running); the caller keeps the row and tries
    again. Existing clients keep their own copy: wg-easy copies the default
    into each client when it is created.
    """
    if not os.path.exists(DB_PATH):
        return False, []
    con = _connect_rw()
    try:
        if not _setup_done(con):
            return False, []
        wanted_json = json.dumps(allowed, separators=(",", ":"))  # stored as a JSON string array
        cur = con.execute(
            "UPDATE user_configs_table SET default_allowed_ips = ? WHERE default_allowed_ips != ?",
            (wanted_json, wanted_json),
        )
        con.commit()
    finally:
        con.close()
    if not cur.rowcount:
        return True, []
    return True, [
        event(
            "info",
            "allowed_ips_applied",
            f"default Allowed IPs for new clients set to {', '.join(allowed)} from the board's settings",
            allowed_ips=allowed,
        )
    ]
