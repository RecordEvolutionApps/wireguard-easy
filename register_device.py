"""IronFlock companion process for wg-easy.

Started in the background by entrypoint.sh and running for the container's
lifetime next to the unmodified wg-easy server. It owns all platform
integration; wg-easy itself knows nothing about IronFlock.

Two independent loops:

1. Endpoint sync (every 10 s, needs NO platform connection): keeps wg-easy's
   advertised client Endpoint equal to the tunnel's public UDP endpoint and
   re-applies the Allowed-IPs parameter (endpoint_sync.py). It must keep
   working when the router is unreachable, e.g. in corporate networks where
   only the tunnel itself gets out.
2. State publishing (every 30 s, once connected): collects the gateway's
   state (vpn_state.py) and writes it to the app's tables on change:
   `gateways` (this device's row), `clients` (one row per VPN client),
   `checks` (the setup checklist), `traffic` (per-minute transfer rates) and
   `events` (what happened). The board and the AI assistant read them.

Once the connection is up, the VPN diagnostics tools and the knowledge
library are registered as device functions for the AI assistant
(ai_tools.py). The SDK restores them after every reconnect.
"""

import asyncio
import collections
import os
import signal
import sys
import time
import traceback

# Printed before the heavy imports so the container log shows whether the
# companion started at all, even when an import below fails.
print(f"[ironflock] companion starting (python {sys.version.split()[0]})", flush=True)
try:
    from ironflock import IronFlock

    import ai_tools
    import endpoint_sync
    import vpn_state
except Exception:
    print("[ironflock] companion failed to import its modules:\n" + traceback.format_exc(), flush=True)
    raise

SYNC_INTERVAL = 10  # s; the agent updates /data/env within seconds of a tunnel toggle
STATE_INTERVAL = 30  # s between state snapshots
TRAFFIC_INTERVAL = 60  # s between traffic samples
HANDSHAKE_REFRESH = 600  # s; re-publish a connected client's row at least this often
STARTUP_GRACE = 90  # s to wait for wg-easy (Web UI and wg interface) before the first state row
PRODUCTION = os.environ.get("ENV", "").upper() == "PROD"

GATEWAY_COLUMNS = (
    "status", "status_detail", "wg_easy_version", "interface_up", "listen_port", "setup_done",
    "db_persisted", "ip_forward", "nat_masquerade", "tunnel_active", "vpn_host", "vpn_port",
    "vpn_endpoint", "ipv4_cidr", "lan_device", "mtu", "default_allowed_ips", "default_dns",
    "clients_total", "clients_enabled", "clients_connected",
)
CLIENT_COLUMNS = (
    "client_id", "name", "enabled", "ipv4", "ipv6", "allowed_ips", "uses_default_allowed_ips",
    "expires_at", "status", "connected", "last_handshake", "rx_bytes", "tx_bytes", "public_key", "deleted",
)
# the part of a client row whose change is worth a new row (counters are not)
CLIENT_STATE = ("name", "enabled", "ipv4", "ipv6", "allowed_ips", "uses_default_allowed_ips", "expires_at", "status")

flock: IronFlock  # assigned in __main__
events: collections.deque = collections.deque(maxlen=500)
refresh_now: asyncio.Event


def log(message: str) -> None:
    print(f"[ironflock] {message}", flush=True)


def queue_event(level: str, kind: str, message: str, **detail) -> None:
    log(f"event {kind}: {message}")
    events.append({"tsp": vpn_state.now_iso(), "level": level, "kind": kind, "message": message, "detail": detail or None})


# --- loop 1: endpoint sync, independent of the platform connection ----------


def resync_endpoint() -> list[dict]:
    """One sync pass; used by the loop and by the AI tool."""
    return endpoint_sync.sync_endpoint_once(endpoint_sync.get_vpn_endpoint(flock))


async def endpoint_sync_loop() -> None:
    log(f"endpoint sync: keeping {vpn_state.DB_PATH} in step with the tunnel (every {SYNC_INTERVAL}s)")
    allowed_ips_done = False
    while True:
        try:
            changed = await asyncio.to_thread(resync_endpoint)
            if not allowed_ips_done:
                allowed_ips_done, more = await asyncio.to_thread(endpoint_sync.sync_allowed_ips_once)
                changed += more
            for e in changed:
                queue_event(e["level"], e["kind"], e["message"], **e["detail"])
            if changed:
                refresh_now.set()
        except Exception as exc:  # locked DB, missing table, ... retry next tick
            log(f"endpoint sync: skipped ({exc})")
        await asyncio.sleep(SYNC_INTERVAL)


# --- loop 2: state publishing ----------------------------------------------


class Publisher:
    """Writes state rows on change and remembers what was written."""

    def __init__(self):
        self.gateway = None
        self.clients: dict[int, dict] = {}
        self.client_published_at: dict[int, float] = {}
        self.checks: dict[str, dict] = {}
        self.traffic: dict[int, tuple[float, int, int]] = {}
        self.last_traffic = 0.0
        self.web_url = None
        self.primed = False  # True after the first complete tick: changes become events

    async def flush_events(self) -> None:
        while events:
            row = events[0]
            try:
                await flock.append_to_table("events", row)
            except RuntimeError as exc:
                log(f"events: not recorded yet ({exc})")
                return
            events.popleft()

    async def publish_gateway(self, snap: dict) -> None:
        row = {k: snap.get(k) for k in GATEWAY_COLUMNS}
        # Published in development runs too: they have their own HTTPS tunnel (label suffix -dev).
        web_url = endpoint_sync.get_web_ui_url(flock)
        row["web_url"] = web_url
        if row == self.gateway:
            return
        if self.gateway is not None and row["status"] != self.gateway["status"]:
            level = "info" if row["status"] == "OK" else "warning"
            queue_event(level, "status_changed", f"gateway status {self.gateway['status']} -> {row['status']}: {row['status_detail']}")
        await flock.append_to_table("gateways", {"tsp": snap["tsp"], **row})
        log(f"state: gateway row published (status {row['status']}: {row['status_detail']})")
        self.gateway = row
        if web_url != self.web_url:
            log(f"web UI url: {web_url or 'unknown (DEVICE_KEY or APP_NAME missing)'}")
            self.web_url = web_url

    async def publish_clients(self, snap: dict, now: float) -> None:
        current = {c["client_id"]: c for c in snap["clients"]}
        for cid, c in current.items():
            previous = self.clients.get(cid)
            state = {k: c[k] for k in CLIENT_STATE}
            stale = c["connected"] and now - self.client_published_at.get(cid, 0) > HANDSHAKE_REFRESH
            if previous is not None and state == previous and not stale:
                continue
            if previous is None and self.primed:
                queue_event("info", "client_added", f"client '{c['name']}' created ({c['ipv4']})", client_id=cid)
            elif previous is not None and previous["status"] != c["status"]:
                if c["status"] == "CONNECTED":
                    queue_event("info", "client_connected", f"client '{c['name']}' connected", client_id=cid)
                elif previous["status"] == "CONNECTED":
                    queue_event("info", "client_disconnected", f"client '{c['name']}' disconnected ({c['status'].lower()})", client_id=cid)
                else:
                    queue_event("info", "client_changed", f"client '{c['name']}' is now {c['status'].lower()}", client_id=cid)
            await flock.append_to_table("clients", {"tsp": snap["tsp"], **{k: c[k] for k in CLIENT_COLUMNS}})
            self.clients[cid] = state
            self.client_published_at[cid] = now
        for cid in list(self.clients):
            if cid in current:
                continue
            previous = self.clients.pop(cid)
            self.client_published_at.pop(cid, None)
            self.traffic.pop(cid, None)
            queue_event("info", "client_removed", f"client '{previous['name']}' removed", client_id=cid)
            await flock.append_to_table(
                "clients",
                {"tsp": snap["tsp"], "client_id": cid, "name": previous["name"], "status": "REMOVED",
                 "connected": False, "enabled": False, "deleted": True},
            )

    async def publish_checks(self, snap: dict) -> None:
        current = {c["check_id"]: c for c in snap["checks"]}
        for check_id, c in current.items():
            if self.checks.get(check_id) == c:
                continue
            await flock.append_to_table("checks", {"tsp": snap["tsp"], **c})
            self.checks[check_id] = c
        for check_id in list(self.checks):
            if check_id in current:
                continue
            cleared = {**self.checks.pop(check_id), "result": vpn_state.OK, "message": "cleared", "hint": ""}
            await flock.append_to_table("checks", {"tsp": snap["tsp"], **cleared})

    async def publish_traffic(self, snap: dict, now: float) -> None:
        if now - self.last_traffic < TRAFFIC_INTERVAL:
            return
        rows = []
        for c in snap["clients"]:
            cid, rx, tx = c["client_id"], c["rx_bytes"], c["tx_bytes"]
            previous = self.traffic.get(cid)
            self.traffic[cid] = (now, rx, tx)
            if previous is None:
                continue
            t0, rx0, tx0 = previous
            if (rx, tx) == (rx0, tx0):
                continue  # idle client: no row
            dt = max(now - t0, 1.0)
            # counters reset when the interface restarts: a negative delta is a restart
            rx_rate = max(rx - rx0, 0) / dt / 1000
            tx_rate = max(tx - tx0, 0) / dt / 1000
            rows.append({"tsp": snap["tsp"], "client_id": cid, "client_name": c["name"], "rx_bytes": rx,
                         "tx_bytes": tx, "rx_kbs": round(rx_rate, 3), "tx_kbs": round(tx_rate, 3)})
        self.last_traffic = now
        if rows:
            await flock.publish_rows_to_table("traffic", rows)


def wg_easy_up() -> bool:
    return vpn_state.web_ui_listening() and vpn_state.wg_dump() is not None


async def wait_for_wg_easy() -> None:
    """Hold back the first state row until wg-easy has started, so a restart
    does not publish a transient PROBLEM (interface down, Web UI not answering)
    with its status_changed event. Gives up after STARTUP_GRACE seconds, e.g.
    on a gateway whose setup is unfinished, and publishes whatever is true."""
    deadline = time.monotonic() + STARTUP_GRACE
    while time.monotonic() < deadline:
        if await asyncio.to_thread(wg_easy_up):
            return
        await asyncio.sleep(2)
    log(f"state: wg-easy not fully up after {STARTUP_GRACE}s; publishing the state as it is")


async def state_loop(publisher: Publisher) -> None:
    await wait_for_wg_easy()
    while True:
        refresh_now.clear()
        now = time.time()
        try:
            snap = await asyncio.to_thread(vpn_state.collect, endpoint_sync.get_vpn_endpoint(flock))
            await publisher.publish_gateway(snap)
            await publisher.publish_checks(snap)
            await publisher.publish_clients(snap, now)
            await publisher.publish_traffic(snap, now)
            await publisher.flush_events()
            publisher.primed = True
        except RuntimeError as exc:  # platform unreachable for the reconnect window: retry next tick
            log(f"state: not recorded ({exc})")
            if "no_such_procedure" in str(exc):
                log(
                    "state: the data backend serves no such table yet. The tables of data-template.yml "
                    "are created by 'Update Data Structure' in the Cloud IDE (development runs) or by "
                    "installing a release; the app retries every tick"
                )
        except Exception as exc:
            log(f"state: failed ({exc!r})")
        try:
            await asyncio.wait_for(refresh_now.wait(), timeout=STATE_INTERVAL)
        except asyncio.TimeoutError:
            pass


# --- main ---------------------------------------------------------------------


async def main() -> None:
    """Runs once the connection is up. It must never return: returning would
    close the connection and with it every registered device function."""
    log("connected to the IronFlock router")
    tools = ai_tools.VpnTools(flock, lambda: endpoint_sync.get_vpn_endpoint(flock), resync_endpoint)
    await ai_tools.register_all(flock, tools, log)
    queue_event("info", "startup", f"gateway companion started (wg-easy {vpn_state.WG_EASY_VERSION})",
                production=PRODUCTION)
    await state_loop(Publisher())


async def run() -> None:
    global refresh_now
    refresh_now = asyncio.Event()
    sync_task = asyncio.create_task(endpoint_sync_loop())
    try:
        await flock.run_async()  # connects (retrying forever), runs main(), never returns
    except Exception as exc:
        log(f"platform connection ended ({exc}); endpoint sync continues")
        await sync_task  # keep the VPN endpoint correct even without the platform
    finally:
        sync_task.cancel()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    try:
        flock = IronFlock(mainFunc=main)
        asyncio.run(run())
    except SystemExit:
        raise
    except BaseException:
        # stdout on purpose: some log views show only stdout, and a silent
        # death here would leave the VPN endpoint unsynced without a trace.
        print("[ironflock] companion crashed:\n" + traceback.format_exc(), flush=True)
        raise
