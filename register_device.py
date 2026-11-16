"""IronFlock companion process for wg-easy.

Started in the background by entrypoint.sh and running for the container's
lifetime next to the unmodified wg-easy server. It owns all platform
integration; wg-easy itself knows nothing about IronFlock. The design is in
design/architecture.md.

Two independent loops:

1. Endpoint sync (every 10 s, needs NO platform connection): keeps wg-easy's
   advertised client Endpoint equal to the tunnel's public UDP endpoint
   (endpoint_sync.py), and applies the settings users save on the board once
   wg-easy is ready. It must keep working when the router is unreachable, e.g.
   in corporate networks where only the tunnel itself gets out.
2. State publishing (every 30 s, once connected): collects the gateway's
   state (vpn_state.py) and writes what changed to the app's tables:
   `gateways` (this gateway's row), `clients` (one row per VPN client),
   `checks` (the setup checklist), `traffic` (per-minute transfer rates) and
   `events` (what happened). The board and the AI assistant read them.

Board-written state this gateway follows: `gateway_settings` (its default
Allowed IPs), and `gateways` rows with deleted = true (a gateway removed on
the board), after which it refreshes the fleet_summary transform.

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
from datetime import datetime

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
REGISTER_RETRY = 30  # s between attempts to write the registration row
PRODUCTION = os.environ.get("ENV", "").upper() == "PROD"
# The key of this gateway in the gateways table. The platform's device_key
# column cannot serve: it is stamped from the writer, and the board's delete
# row has no device. 0 only outside IronFlock, where nothing is published.
DEVICE_ID = int(os.environ.get("DEVICE_KEY") or 0)
DEVICE_NAME = os.environ.get("DEVICE_NAME") or f"device {DEVICE_ID}"
SETTINGS_STATE = "/data/.ironflock_settings_tsp"  # tsp (epoch ms) of the settings row applied last
FLEET_SUMMARY = "fleet_summary"

GATEWAY_COLUMNS = (
    "status", "status_detail", "wg_easy_version", "interface_up", "listen_port", "setup_done",
    "db_persisted", "ip_forward", "nat_masquerade", "tunnel_active", "vpn_host", "vpn_port",
    "vpn_endpoint", "ipv4_cidr", "lan_device", "mtu", "default_allowed_ips", "default_dns",
    "clients_total", "clients_enabled", "clients_connected",
)
CLIENT_COLUMNS = (
    "client_id", "name", "enabled", "ipv4", "ipv6", "allowed_ips", "uses_default_allowed_ips",
    "expires_at", "status", "connected", "last_handshake", "rx_bytes", "tx_bytes", "public_key",
)
# the part of a client row whose change is worth a new row (counters are not)
CLIENT_STATE = ("name", "enabled", "ipv4", "ipv6", "allowed_ips", "uses_default_allowed_ips", "expires_at", "status")

flock: IronFlock  # assigned in __main__
events: collections.deque = collections.deque(maxlen=500)
refresh_now: asyncio.Event  # wakes the state loop
sync_now: asyncio.Event  # wakes the endpoint sync loop


def log(message: str) -> None:
    print(f"[ironflock] {message}", flush=True)


def client_key(client_id: int) -> str:
    """The client's key across all gateways: wg-easy numbers clients per gateway."""
    return f"{DEVICE_ID}-{client_id}"


def queue_event(level: str, kind: str, message: str, client: str | None = None, **detail) -> None:
    log(f"event {kind}: {message}")
    events.append({
        "tsp": vpn_state.now_iso(), "device_id": DEVICE_ID, "client_key": client,
        "level": level, "kind": kind, "message": message, "detail": detail or None,
    })


async def refresh_fleet_summary() -> None:
    """Push the home page's figures to open boards now instead of at the next tick."""
    try:
        await flock.refresh_transform(FLEET_SUMMARY)
    except Exception as exc:  # URI_REFRESH_IN_PROGRESS, platform away: the schedule catches up
        log(f"{FLEET_SUMMARY}: not refreshed now ({exc}); its schedule refreshes it within a minute")


# --- settings written on the board -----------------------------------------


def tsp_ms(value) -> float | None:
    """A row's tsp as epoch milliseconds; reads return epoch ms, be tolerant of ISO."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
        except ValueError:
            return None
    return None


class Settings:
    """The gateway_settings row in force for this gateway.

    Rows come from the first read and from the subscription, and a row saved
    just as the program starts can come from both, so only a row newer than
    the one applied last is taken. That tsp is kept on /data: a restart does
    not re-apply an old row over a later edit in the Web UI."""

    def __init__(self):
        self.applied_tsp = self._load()
        self.pending: dict | None = None

    @staticmethod
    def _load() -> float:
        try:
            with open(SETTINGS_STATE) as f:
                return float(f.read().strip() or 0)
        except (OSError, ValueError):
            return 0.0

    def _mark_applied(self, tsp: float) -> None:
        self.applied_tsp = tsp
        self.pending = None
        try:
            with open(SETTINGS_STATE, "w") as f:
                f.write(repr(tsp))
        except OSError as exc:
            log(f"settings: could not store the applied tsp ({exc})")

    def offer(self, row: dict) -> None:
        try:
            if int(float(row.get("device_id"))) != DEVICE_ID:
                return  # another gateway's settings
        except (TypeError, ValueError):
            return
        tsp = tsp_ms(row.get("tsp"))
        if tsp is None or tsp <= self.applied_tsp:
            return
        if self.pending is not None and tsp <= tsp_ms(self.pending.get("tsp")):
            return
        self.pending = row
        log(f"settings: new default Allowed IPs saved on the board: {row.get('default_allowed_ips')!r}")
        sync_now.set()

    async def apply_pending(self) -> list[dict]:
        """Apply the pending row once wg-easy is ready; returns its events."""
        row = self.pending
        if row is None:
            return []
        tsp = tsp_ms(row.get("tsp"))
        try:
            allowed = endpoint_sync.parse_allowed_ips(row.get("default_allowed_ips"))
        except ValueError as exc:
            self._mark_applied(tsp)  # a wrong value stays wrong: do not retry it
            message = f"default Allowed IPs not applied: {exc}"
            asyncio.ensure_future(report_rejected(f"{DEVICE_NAME}: {message}"))
            return [endpoint_sync.event("warning", "settings_rejected", message,
                                        value=row.get("default_allowed_ips"))]
        done, changed = await asyncio.to_thread(endpoint_sync.apply_default_allowed_ips, allowed)
        if done:
            self._mark_applied(tsp)
        return changed


async def report_rejected(user_message: str) -> None:
    try:
        await flock.report_error(user_message, level="warning", user_message=user_message)
    except Exception as exc:
        log(f"settings: could not report the rejection ({exc})")


settings = Settings()


async def on_settings(row, *args, **kwargs) -> None:
    """A gateway_settings row the board saved. Rows saved while this gateway
    was offline arrive too: the SDK delivers them once the connection is back."""
    if isinstance(row, dict):
        settings.offer(row)


async def on_gateway_row(row, *args, **kwargs) -> None:
    """A gateways row from any gateway or from the board. deleted = true comes
    only from the board's "Remove gateway"; the home figures drop it now."""
    if isinstance(row, dict) and row.get("deleted") is True:
        await refresh_fleet_summary()


# --- loop 1: endpoint sync, independent of the platform connection ----------


def resync_endpoint() -> list[dict]:
    """One sync pass; used by the loop and by the AI tool."""
    return endpoint_sync.sync_endpoint_once(endpoint_sync.get_vpn_endpoint(flock))


async def endpoint_sync_loop() -> None:
    log(f"endpoint sync: keeping {vpn_state.DB_PATH} in step with the tunnel (every {SYNC_INTERVAL}s)")
    while True:
        sync_now.clear()
        try:
            changed = await asyncio.to_thread(resync_endpoint)
            changed += await settings.apply_pending()
            for e in changed:
                queue_event(e["level"], e["kind"], e["message"], **e["detail"])
            if changed:
                refresh_now.set()
        except Exception as exc:  # locked DB, missing table, ... retry next tick
            log(f"endpoint sync: skipped ({exc})")
        try:
            await asyncio.wait_for(sync_now.wait(), timeout=SYNC_INTERVAL)
        except asyncio.TimeoutError:
            pass


# --- loop 2: state publishing ----------------------------------------------


def changed_columns(new: dict, old: dict | None) -> dict:
    """The columns of `new` that differ from what was written last."""
    if old is None:
        return dict(new)
    return {k: v for k, v in new.items() if k not in old or old[k] != v}


class Publisher:
    """Writes state rows on change and remembers what was written.

    Entity rows hold the key, a tsp and the columns that changed: the platform
    carries the other columns over from the entity's previous row."""

    def __init__(self):
        self.gateway: dict | None = None  # columns written to gateways since the registration
        self.clients: dict[int, dict] = {}  # client_id -> columns written
        self.client_published_at: dict[int, float] = {}
        self.checks: dict[str, dict] = {}
        self.traffic: dict[int, tuple[float, int, int]] = {}
        self.last_traffic = 0.0
        self.primed = False  # True after the first complete tick: changes become events

    async def register(self) -> None:
        """This gateway's registration row. deleted = false brings back a
        gateway a user removed on the board, now that it runs the app again;
        the state rows leave the column out and keep a removal in force. A
        development run writes the URL of its own -dev tunnel."""
        web_url = endpoint_sync.get_web_ui_url(flock)
        row = {
            "tsp": vpn_state.now_iso(), "device_id": DEVICE_ID, "device_name": DEVICE_NAME,
            "deleted": False, "web_url": web_url, "wg_easy_version": vpn_state.WG_EASY_VERSION,
        }
        while True:
            try:
                await flock.append_to_table("gateways", row)
                break
            except RuntimeError as exc:
                log(f"registration: not recorded yet ({exc}); retrying in {REGISTER_RETRY}s")
                await asyncio.sleep(REGISTER_RETRY)
        self.gateway = {"web_url": web_url, "wg_easy_version": vpn_state.WG_EASY_VERSION}
        log(f"registered as gateway {DEVICE_ID} ({DEVICE_NAME}); web UI url: {web_url or 'unknown'}")

    async def flush_events(self) -> None:
        while events:
            row = events[0]
            try:
                await flock.append_to_table("events", row)
            except RuntimeError as exc:
                log(f"events: not recorded yet ({exc})")
                return
            events.popleft()

    async def publish_gateway(self, snap: dict) -> bool:
        """Returns True when a row was written."""
        full = {k: snap.get(k) for k in GATEWAY_COLUMNS}
        full["web_url"] = endpoint_sync.get_web_ui_url(flock)
        changed = changed_columns(full, self.gateway)
        if not changed:
            return False
        previous = (self.gateway or {}).get("status")
        if previous is not None and "status" in changed:
            level = "info" if full["status"] == "OK" else "warning"
            queue_event(level, "status_changed", f"gateway status {previous} -> {full['status']}: {full['status_detail']}")
        await flock.append_to_table("gateways", {"tsp": snap["tsp"], "device_id": DEVICE_ID, **changed})
        if "status" in changed or "status_detail" in changed:
            log(f"state: gateway status {full['status']}: {full['status_detail']}")
        self.gateway = {**(self.gateway or {}), **changed}
        return True

    async def publish_clients(self, snap: dict, now: float) -> None:
        current = {c["client_id"]: c for c in snap["clients"]}
        for cid, c in current.items():
            key = client_key(cid)
            full = {k: c[k] for k in CLIENT_COLUMNS}
            full["display_name"] = f"{c['name']} · {DEVICE_NAME}"
            previous = self.clients.get(cid)
            stale = c["connected"] and now - self.client_published_at.get(cid, 0) > HANDSHAKE_REFRESH
            if previous is not None and not stale and all(previous[k] == full[k] for k in CLIENT_STATE):
                continue
            if previous is None and self.primed:
                queue_event("info", "client_added", f"client '{c['name']}' created ({c['ipv4']})", client=key, client_id=cid)
            elif previous is not None and previous["status"] != c["status"]:
                if c["status"] == "CONNECTED":
                    queue_event("info", "client_connected", f"client '{c['name']}' connected", client=key, client_id=cid)
                elif previous["status"] == "CONNECTED":
                    queue_event("info", "client_disconnected", f"client '{c['name']}' disconnected ({c['status'].lower()})", client=key, client_id=cid)
                else:
                    queue_event("info", "client_changed", f"client '{c['name']}' is now {c['status'].lower()}", client=key, client_id=cid)
            if previous is None:
                # the client's first row in this run: its registration
                row = {"client_key": key, "device_id": DEVICE_ID, "device_name": DEVICE_NAME, "deleted": False, **full}
            else:
                row = {"client_key": key, **changed_columns(full, previous)}
            await flock.append_to_table("clients", {"tsp": snap["tsp"], **row})
            self.clients[cid] = full
            self.client_published_at[cid] = now
        for cid in list(self.clients):
            if cid in current:
                continue
            previous = self.clients[cid]
            key = client_key(cid)
            await flock.append_to_table(
                "clients",
                {"tsp": snap["tsp"], "client_key": key, "status": "REMOVED",
                 "connected": False, "enabled": False, "deleted": True},
            )
            queue_event("info", "client_removed", f"client '{previous['name']}' removed", client=key, client_id=cid)
            del self.clients[cid]
            self.client_published_at.pop(cid, None)
            self.traffic.pop(cid, None)

    async def publish_checks(self, snap: dict) -> None:
        current = {c["check_id"]: c for c in snap["checks"]}
        for check_id, c in current.items():
            changed = changed_columns(c, self.checks.get(check_id))
            if not changed:
                continue
            await flock.append_to_table("checks", {"tsp": snap["tsp"], "device_id": DEVICE_ID, "check_id": check_id, **changed})
            self.checks[check_id] = c
        for check_id in list(self.checks):
            if check_id in current:
                continue
            await flock.append_to_table(
                "checks",
                {"tsp": snap["tsp"], "device_id": DEVICE_ID, "check_id": check_id,
                 "result": vpn_state.OK, "message": "cleared", "hint": ""},
            )
            del self.checks[check_id]

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
            rows.append({"tsp": snap["tsp"], "device_id": DEVICE_ID, "client_key": client_key(cid),
                         "client_id": cid, "client_name": c["name"], "rx_bytes": rx, "tx_bytes": tx,
                         "rx_kbs": round(rx_rate, 3), "tx_kbs": round(tx_rate, 3)})
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
            gateway_written = await publisher.publish_gateway(snap)
            await publisher.publish_checks(snap)
            await publisher.publish_clients(snap, now)
            await publisher.publish_traffic(snap, now)
            await publisher.flush_events()
            publisher.primed = True
            if gateway_written:
                await refresh_fleet_summary()
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


async def read_saved_settings() -> None:
    """The newest settings row saved for this gateway, read once at start.
    Retried until it succeeds: the subscription only delivers later rows."""
    query = {
        "limit": 1,
        "filterAnd": [
            {"latest": True},
            {"column": "device_id", "operator": "=", "value": DEVICE_ID, "dataType": "numeric"},
        ],
    }
    while True:
        try:
            rows = await flock.getHistory("gateway_settings", query)
            break
        except Exception as exc:
            log(f"settings: reading the saved settings failed ({exc}); retrying in {REGISTER_RETRY}s")
            await asyncio.sleep(REGISTER_RETRY)
    for row in rows or []:
        settings.offer(row)


async def follow_board() -> None:
    """Follow what the board writes: subscribe first, so no row falls between
    the read and the subscription, then read the newest settings row."""
    await flock.subscribe_to_table("gateway_settings", on_settings)
    await flock.subscribe_to_table("gateways", on_gateway_row)
    await read_saved_settings()


async def main() -> None:
    """Runs once the connection is up. It must never return: returning would
    close the connection and with it every registered device function."""
    log("connected to the IronFlock router")
    if not DEVICE_ID:
        log("DEVICE_KEY is not set: not an IronFlock device, nothing is published")
        await asyncio.Event().wait()
    tools = ai_tools.VpnTools(flock, lambda: endpoint_sync.get_vpn_endpoint(flock), resync_endpoint)
    await ai_tools.register_all(flock, tools, log)
    publisher = Publisher()
    await publisher.register()
    await refresh_fleet_summary()  # a gateway that was removed counts again at once
    await follow_board()
    queue_event("info", "startup", f"gateway companion started (wg-easy {vpn_state.WG_EASY_VERSION})",
                production=PRODUCTION)
    await state_loop(publisher)


async def run() -> None:
    global refresh_now, sync_now
    refresh_now = asyncio.Event()
    sync_now = asyncio.Event()
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
