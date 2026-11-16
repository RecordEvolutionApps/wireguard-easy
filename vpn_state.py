"""Read-only view of this gateway's VPN state.

Everything the board tables, the setup checklist and the AI tools report is
collected here from four local sources, none of which needs the platform:

- wg-easy's SQLite database (/data/wg-easy.db): setup state, interface,
  the advertised client endpoint, defaults, and the configured clients;
- `wg show <interface> dump`: the live interface (ListenPort) and per-peer
  handshake and transfer counters;
- the kernel (sysctl, iptables): forwarding and NAT masquerading;
- the local Web UI port.

`collect()` merges them into one snapshot dict with the gateway status, the
client list and the setup checklist. It never raises: a source that cannot be
read shows up as a check result instead.
"""

import ipaddress
import json
import os
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

DB_PATH = "/data/wg-easy.db"  # /etc/wireguard -> /data (entrypoint.sh)
SETTINGS_DIR = "/etc/wireguard"
DATA_DIR = "/data"
VPN_PORT = 51820  # the wg ListenPort; must match port-template.yml
WEB_UI_PORT = 51821  # must match port-template.yml
INTERFACE = os.environ.get("WG_INTERFACE") or "wg0"
WG_EASY_VERSION = os.environ.get("WG_EASY_VERSION") or "unknown"
# A WireGuard peer re-handshakes at least every 2 minutes while traffic flows.
CONNECTED_WINDOW_SECONDS = 180

OK, INFO, WARNING, PROBLEM = "OK", "INFO", "WARNING", "PROBLEM"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def epoch_to_iso(epoch) -> str | None:
    if not epoch:
        return None
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()


def parse_list(value) -> list[str]:
    """wg-easy stores list columns as JSON arrays; tolerate comma strings too."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if text.startswith("["):
        try:
            return [str(v).strip() for v in json.loads(text) if str(v).strip()]
        except ValueError:
            pass
    return [x.strip() for x in text.split(",") if x.strip()]


def parse_expiry(value) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for candidate in (text, text + "T00:00:00+00:00"):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


# --- sources -----------------------------------------------------------------


def db_persisted() -> bool:
    return os.path.islink(SETTINGS_DIR) and os.path.realpath(SETTINGS_DIR) == os.path.realpath(DATA_DIR)


def read_db() -> dict | None:
    """wg-easy's configuration, or None while the database does not exist yet.

    Opens the DB read-only; raises sqlite3.Error when it is locked for longer
    than 5 s or its schema is not there yet (first boot: migrations running).
    """
    if not os.path.exists(DB_PATH):
        return None
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        setup = con.execute("SELECT setup_step FROM general_table").fetchone()
        iface = con.execute(
            "SELECT name, device, port, ipv4_cidr, ipv6_cidr, mtu FROM interfaces_table"
        ).fetchone()
        cfg = con.execute(
            "SELECT host, port, default_allowed_ips, default_dns, default_mtu, "
            "default_persistent_keepalive FROM user_configs_table"
        ).fetchone()
        clients = con.execute(
            "SELECT id, name, enabled, ipv4_address, ipv6_address, allowed_ips, "
            "expires_at, public_key, persistent_keepalive, created_at, updated_at "
            "FROM clients_table ORDER BY id"
        ).fetchall()
    finally:
        con.close()
    return {
        "setup_step": None if setup is None else setup["setup_step"],
        "setup_done": setup is not None and setup["setup_step"] == 0,
        "interface": None if iface is None else dict(iface),
        "user_config": None if cfg is None else dict(cfg),
        "clients": [dict(c) for c in clients],
    }


def wg_dump(interface: str = INTERFACE) -> dict | None:
    """Live interface state from `wg show <interface> dump`, or None when the
    interface is not up (or wg is unavailable)."""
    wg = shutil.which("wg") or "/usr/bin/wg"
    try:
        out = subprocess.run([wg, "show", interface, "dump"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    lines = out.stdout.strip().splitlines()
    if not lines:
        return None
    head = lines[0].split("\t")  # private_key public_key listen_port fwmark
    peers = {}
    for line in lines[1:]:
        f = line.split("\t")  # pubkey psk endpoint allowed_ips handshake rx tx keepalive
        if len(f) < 8:
            continue
        peers[f[0]] = {
            "allowed_ips": f[3],
            "latest_handshake": int(f[4]) if f[4].isdigit() and int(f[4]) > 0 else None,
            "rx_bytes": int(f[5]) if f[5].isdigit() else 0,
            "tx_bytes": int(f[6]) if f[6].isdigit() else 0,
            "keepalive": f[7],
        }
    listen_port = int(head[2]) if len(head) > 2 and head[2].isdigit() else None
    return {"listen_port": listen_port, "peers": peers}


def read_sysctl(path: str) -> str | None:
    try:
        with open(f"/proc/sys/{path}") as f:
            return f.read().strip()
    except OSError:
        return None


def nat_masquerade(cidr: str | None) -> bool | None:
    """True when a MASQUERADE rule for the VPN subnet is installed, False when
    not, None when iptables cannot be asked."""
    iptables = shutil.which("iptables") or "/usr/sbin/iptables"
    try:
        out = subprocess.run(
            [iptables, "-t", "nat", "-S", "POSTROUTING"], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    rules = [line for line in out.stdout.splitlines() if "MASQUERADE" in line]
    if not rules:
        return False
    if not cidr:
        return True
    return any(cidr in rule for rule in rules) or any("-s" not in rule for rule in rules)


def web_ui_listening(port: int = WEB_UI_PORT) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3)
        return True
    except urllib.error.HTTPError:
        return True  # it answered, whatever the status
    except (urllib.error.URLError, OSError, ValueError):
        return False


# --- snapshot -----------------------------------------------------------------


def _client_status(enabled: bool, expired: bool, handshake_age: float | None, had_handshake: bool) -> str:
    if not enabled:
        return "DISABLED"
    if expired:
        return "EXPIRED"
    if handshake_age is not None and handshake_age <= CONNECTED_WINDOW_SECONDS:
        return "CONNECTED"
    if had_handshake:
        return "OFFLINE"
    return "NEVER_CONNECTED"


def build_clients(db: dict | None, dump: dict | None, now: float | None = None) -> list[dict]:
    """One dict per configured client, merged with its live peer counters."""
    if not db:
        return []
    now = now or time.time()
    peers = (dump or {}).get("peers", {})
    cfg = db.get("user_config") or {}
    default_allowed = parse_list(cfg.get("default_allowed_ips"))
    rows = []
    for c in db["clients"]:
        peer = peers.get(c["public_key"]) or {}
        handshake = peer.get("latest_handshake")
        age = (now - handshake) if handshake else None
        expiry = parse_expiry(c.get("expires_at"))
        expired = expiry is not None and expiry.timestamp() < now
        own_allowed = parse_list(c.get("allowed_ips"))
        allowed = own_allowed or default_allowed
        enabled = bool(c["enabled"])
        status = _client_status(enabled, expired, age, handshake is not None)
        rows.append(
            {
                "client_id": int(c["id"]),
                "name": c["name"],
                "enabled": enabled,
                "ipv4": c.get("ipv4_address"),
                "ipv6": c.get("ipv6_address"),
                "allowed_ips": ", ".join(allowed),
                "uses_default_allowed_ips": not own_allowed,
                "expires_at": expiry.isoformat() if expiry else None,
                "status": status,
                "connected": status == "CONNECTED",
                "last_handshake": epoch_to_iso(handshake),
                "handshake_age_s": None if age is None else int(age),
                "rx_bytes": int(peer.get("rx_bytes", 0)),
                "tx_bytes": int(peer.get("tx_bytes", 0)),
                "public_key": c["public_key"],
            }
        )
    return rows


def _cidr_covers(cidrs: list[str], network: str) -> bool:
    try:
        target = ipaddress.ip_network(network, strict=False)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if net.version == target.version and target.subnet_of(net):
            return True
    return False


def collect(endpoint: tuple[str, int] | None) -> dict:
    """The gateway's current state: identity, checks, clients and status.

    `endpoint` is the public VPN endpoint the tunnel currently assigns (from
    the SDK), or None while the VPN tunnel is inactive.
    """
    now = time.time()
    checks: list[dict] = []

    def check(check_id, label, result, message, hint=None):
        checks.append(
            {"check_id": check_id, "label": label, "result": result, "message": message, "hint": hint or ""}
        )

    persisted = db_persisted()
    check(
        "db_persisted",
        "Database persists on /data",
        OK if persisted else PROBLEM,
        f"{SETTINGS_DIR} is linked to {DATA_DIR}" if persisted else f"{SETTINGS_DIR} is not linked to {DATA_DIR}",
        None if persisted else "Clients and the admin account would be lost on restart. Reinstall or restart the app; the entrypoint creates the link.",
    )

    db, db_error = None, None
    try:
        db = read_db()
    except sqlite3.Error as exc:
        db_error = str(exc)
    if db is None and db_error is None:
        check("database", "wg-easy database", WARNING, "not created yet: the first start is still initializing", "Wait a minute. If it stays like this, read the container logs.")
    elif db_error:
        check("database", "wg-easy database", WARNING, f"could not be read right now ({db_error})", "Usually a passing lock or a running migration; it is re-checked every 30 s.")
    else:
        check("database", "wg-easy database", OK, f"readable at {DB_PATH}")

    setup_done = bool(db and db["setup_done"])
    if db:
        check(
            "setup_done",
            "First-boot setup",
            OK if setup_done else PROBLEM,
            "complete: the admin account exists" if setup_done else f"not finished (setup step {db['setup_step']})",
            None if setup_done else "The Web UI shows the setup wizard. Either finish it there, or check the Admin Username (min. 2 chars) and Admin Password (min. 12 chars) parameters and reinstall the app with an empty /data.",
        )

    dump = wg_dump()
    check(
        "interface_up",
        f"WireGuard interface {INTERFACE}",
        OK if dump else (WARNING if not setup_done else PROBLEM),
        f"up, ListenPort {dump['listen_port']}" if dump else "not up",
        None if dump else "wg-easy brings the interface up after setup. If setup is complete, read the container logs: \"Operation not permitted\" means the app's privileged access was not granted (project settings); otherwise the host kernel lacks WireGuard support.",
    )

    iface = (db or {}).get("interface") or {}
    cfg = (db or {}).get("user_config") or {}
    db_port = iface.get("port")
    live_port = (dump or {}).get("listen_port")
    if db:
        port_ok = db_port == VPN_PORT and (live_port in (None, VPN_PORT))
        check(
            "listen_port",
            "ListenPort is 51820",
            OK if port_ok else PROBLEM,
            f"configured {db_port}, live {live_port if live_port is not None else 'n/a'}",
            None if port_ok else f"The tunnel forwards the public UDP port to {VPN_PORT} inside the container. The app repairs the stored port automatically; restart the app so the interface picks it up. Never edit Port under Admin Panel > Interface.",
        )

    tunnel_active = endpoint is not None
    check(
        "tunnel_active",
        "VPN tunnel (public UDP port)",
        OK if tunnel_active else WARNING,
        f"assigned: {endpoint[0]}:{endpoint[1]}" if tunnel_active else "no public UDP port is assigned to this device",
        None if tunnel_active else "In IronFlock open the device, Remote Access, and switch the VPN (udp 51820) tunnel on. A development run gets its own UDP port shortly after the container starts.",
    )

    adv_host, adv_port = cfg.get("host"), cfg.get("port")
    if db and tunnel_active:
        synced = (adv_host, adv_port) == endpoint
        check(
            "endpoint_synced",
            "Advertised client endpoint",
            OK if synced else WARNING,
            f"{adv_host}:{adv_port}" + ("" if synced else f" differs from the tunnel {endpoint[0]}:{endpoint[1]}"),
            None if synced else "The app corrects Host and Port within 10 s. Re-download client configs afterwards; configs downloaded earlier carry the old Endpoint.",
        )
    elif db:
        check("endpoint_synced", "Advertised client endpoint", INFO, f"{adv_host}:{adv_port} (kept from the last active tunnel)")

    ip_forward = read_sysctl("net/ipv4/ip_forward")
    check(
        "ip_forward",
        "IPv4 forwarding",
        OK if ip_forward == "1" else PROBLEM,
        f"net.ipv4.ip_forward = {ip_forward}",
        None if ip_forward == "1" else "Clients connect but cannot reach anything. The entrypoint enables it; the container must run privileged (grant the app's privileged access in its project settings).",
    )

    masq = nat_masquerade(iface.get("ipv4_cidr")) if dump else None
    if dump:
        check(
            "nat_masquerade",
            "NAT masquerade for VPN clients",
            OK if masq else (WARNING if masq is False else INFO),
            "MASQUERADE rule installed" if masq else ("no MASQUERADE rule found" if masq is False else "iptables could not be queried"),
            None if masq else f"wg-easy installs it in the interface's PostUp hook for the interface device ({iface.get('device') or 'eth0'}). If the gateway's LAN interface has another name, change the device under Admin Panel > Interface and restart.",
        )

    ui = web_ui_listening()
    check(
        "web_ui",
        "Web UI on port 51821",
        OK if ui else (WARNING if not db else PROBLEM),
        "answers locally" if ui else "does not answer locally",
        None if ui else "wg-easy is still starting or crashed; read the container logs.",
    )

    default_allowed = parse_list(cfg.get("default_allowed_ips"))
    vpn_cidr = iface.get("ipv4_cidr")
    if db and setup_done:
        routes_vpn = vpn_cidr and (_cidr_covers(default_allowed, vpn_cidr) or "0.0.0.0/0" in default_allowed)
        check(
            "default_allowed_ips",
            "Default Allowed IPs for new clients",
            OK if routes_vpn else WARNING,
            ", ".join(default_allowed) or "(empty)",
            None if routes_vpn else f"New clients would not route the VPN subnet {vpn_cidr}. Add it to the default Allowed IPs on the gateway's Settings page of the board (full tunnel: 0.0.0.0/0, ::/0).",
        )

    clients = build_clients(db, dump, now)
    enabled = [c for c in clients if c["enabled"]]
    connected = [c for c in clients if c["connected"]]
    if db and setup_done:
        check(
            "clients",
            "VPN clients",
            OK if enabled else WARNING,
            f"{len(clients)} configured, {len(enabled)} enabled, {len(connected)} connected",
            None if enabled else "Create a client in the Web UI (the + button), download its config or scan the QR code on the laptop or phone, then connect.",
        )
        expired = [c["name"] for c in clients if c["status"] == "EXPIRED"]
        if expired:
            check("expired_clients", "Expired clients", WARNING, ", ".join(expired[:5]), "Expired clients cannot connect. Extend or remove the expiry date in the Web UI.")
        never = [c["name"] for c in enabled if c["status"] == "NEVER_CONNECTED"]
        if never:
            check("never_connected", "Clients that never connected", INFO, ", ".join(never[:5]) + (" ..." if len(never) > 5 else ""), "Normal for a freshly created client. If it stays like this after connecting, check the client's Endpoint and the tunnel.")

    results = {c["result"] for c in checks}
    if db is None:
        status, detail = "STARTING", "wg-easy is initializing its database"
    elif not setup_done:
        status, detail = "SETUP_PENDING", "first-boot setup not finished"
    elif PROBLEM in results:
        status = "PROBLEM"
        detail = "; ".join(c["label"] for c in checks if c["result"] == PROBLEM)
    elif WARNING in results:
        status = "WARNING"
        detail = "; ".join(c["label"] for c in checks if c["result"] == WARNING)
    else:
        status, detail = "OK", f"{len(connected)} of {len(enabled)} enabled clients connected"

    return {
        "tsp": now_iso(),
        "status": status,
        "status_detail": detail,
        "wg_easy_version": WG_EASY_VERSION,
        "interface": INTERFACE,
        "interface_up": dump is not None,
        "listen_port": live_port if live_port is not None else db_port,
        "setup_done": setup_done,
        "db_persisted": persisted,
        "ip_forward": ip_forward == "1",
        "nat_masquerade": masq,
        "tunnel_active": tunnel_active,
        "vpn_host": endpoint[0] if endpoint else None,
        "vpn_port": endpoint[1] if endpoint else None,
        "vpn_endpoint": f"{endpoint[0]}:{endpoint[1]}" if endpoint else None,
        "advertised_host": adv_host,
        "advertised_port": adv_port,
        "ipv4_cidr": vpn_cidr,
        "ipv6_cidr": iface.get("ipv6_cidr"),
        "lan_device": iface.get("device"),
        "mtu": iface.get("mtu"),
        "default_allowed_ips": ", ".join(default_allowed) or None,
        "default_dns": ", ".join(parse_list(cfg.get("default_dns"))) or None,
        "default_persistent_keepalive": cfg.get("default_persistent_keepalive"),
        "clients_total": len(clients),
        "clients_enabled": len(enabled),
        "clients_connected": len(connected),
        "checks": checks,
        "clients": clients,
    }


def route_check(snapshot: dict, client_name: str, target: str) -> dict:
    """Would `target` be routed through the VPN by this client, and could the
    gateway deliver it? Pure computation on a snapshot."""
    clients = snapshot.get("clients", [])
    wanted = (client_name or "").strip().lower()
    client = next((c for c in clients if c["name"].lower() == wanted), None)
    if client is None:
        return {
            "found": False,
            "error": f"No client named {client_name!r}.",
            "available_clients": sorted(c["name"] for c in clients),
        }
    try:
        target_ip = ipaddress.ip_address(target.strip())
    except ValueError:
        return {"found": True, "client": client["name"], "error": f"{target!r} is not an IP address. Pass the machine's IPv4 address, e.g. 192.168.0.123."}

    allowed = parse_list(client["allowed_ips"])
    matched = []
    for cidr in allowed:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if net.version == target_ip.version and target_ip in net:
            matched.append(str(net))
    vpn_cidr = snapshot.get("ipv4_cidr")
    in_vpn_subnet = bool(vpn_cidr) and _cidr_covers([vpn_cidr], f"{target_ip}/32") if target_ip.version == 4 else False
    full_tunnel = any(c in ("0.0.0.0/0", "::/0") for c in allowed)
    lan_ip = os.environ.get("DEVICE_LAN_IP")
    same_lan = None
    if lan_ip and target_ip.version == 4:
        try:
            same_lan = ipaddress.ip_address(lan_ip) in ipaddress.ip_network(f"{target_ip}/24", strict=False)
        except ValueError:
            same_lan = None

    findings = []
    if matched:
        findings.append(f"{target_ip} is routed through the VPN by this client (matches {', '.join(matched)}).")
    else:
        findings.append(
            f"{target_ip} is NOT routed through the VPN: the client's Allowed IPs ({', '.join(allowed) or 'empty'}) do not cover it. "
            f"Add {target_ip}/32 (one machine) or the machine's subnet in the Web UI, then re-download the client config."
        )
    if full_tunnel:
        findings.append("This client is a full tunnel (0.0.0.0/0): all of its traffic, including internet, goes through the gateway.")
    if in_vpn_subnet:
        findings.append(f"{target_ip} lies in the VPN subnet {vpn_cidr}: it is another VPN client or the gateway itself, not a machine on the LAN.")
    elif same_lan is True:
        findings.append(f"{target_ip} is on the same /24 as the gateway's LAN address {lan_ip}; the gateway can masquerade traffic to it.")
    elif same_lan is False:
        findings.append(f"{target_ip} is not on the gateway's LAN /24 ({lan_ip}); the gateway needs a route to that network for the machine to be reachable.")
    if vpn_cidr and not (_cidr_covers(allowed, vpn_cidr) or full_tunnel):
        findings.append(f"The client's Allowed IPs do not include the VPN subnet {vpn_cidr}; add it so the client can reach the gateway and other clients.")
    if client["status"] != "CONNECTED":
        findings.append(f"The client is currently {client['status']}; the route only matters once it connects.")
    return {
        "found": True,
        "client": client["name"],
        "client_status": client["status"],
        "target": str(target_ip),
        "routed_through_vpn": bool(matched),
        "matching_allowed_ips": matched,
        "client_allowed_ips": allowed,
        "vpn_subnet": vpn_cidr,
        "gateway_lan_ip": lan_ip,
        "findings": findings,
    }
