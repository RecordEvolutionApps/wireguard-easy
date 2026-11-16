# Architecture

## The parts

| Part | Where it runs | What it does |
|---|---|---|
| wg-easy (`ghcr.io/wg-easy/wg-easy`, version pinned in `Dockerfile`) | the container on every gateway, as the main process | the WireGuard server and its admin Web UI on port 51821; keeps its state in SQLite at `/data/wg-easy.db` |
| `entrypoint.sh` | the same container, PID 1 until it `exec`s wg-easy | sysctls, `/etc/wireguard -> /data`, first-boot `INIT_*` values, startup banner, starts the companion in a restart loop |
| The companion (`register_device.py` with `endpoint_sync.py`, `vpn_state.py`, `ai_tools.py`) | the same container, in the background | all platform integration: keeps the client endpoint in step with the tunnel, applies the board's settings, writes the gateway's state to the tables, serves the AI tools |
| The app's tables (`.ironflock/data-template.yml`) | the project's database | all state the board and the AI assistant see |
| The board (`.ironflock/board-template.yml`) | IronFlock, in the browser | the app's UI, bound to the tables live; embeds each gateway's wg-easy Web UI |
| The AI agent (`.ironflock/ai-template.yml`, `knowledge/`) | the IronFlock assistant | diagnoses gateways and clients through the device functions and SQL over the tables |

The companion and the board never call each other: both read and write the
tables. The AI assistant calls the device functions on one gateway.

## Tables and their writers

| Table | Kind | Written by | Read by |
|---|---|---|---|
| `gateways` | entity table, `maintainLatestFlagFor: [device_id]` | each gateway about itself: registration at start (`device_id`, `device_name`, `web_url`, `deleted: false`), then the columns that changed; the board's "Remove gateway" form writes `deleted: true` only | board, `fleet_summary`, AI |
| `gateway_settings` | entity table, `[device_id]` | the board's settings form | the gateway it names, which applies it |
| `clients` | entity table, `[client_key]` | the gateway that has the client: first row per run with `deleted: false`, then the changed columns, `deleted: true` once removed in wg-easy; the board's "Remove from list" form writes `deleted: true` only | board, AI |
| `checks` | entity table, `[device_id, check_id]` | each gateway, when a check's result changes | board, AI |
| `traffic` | readings, 1 min, `dropAfter: 90 days`, downsampled for a year | each gateway, only for clients whose counters moved | board, AI |
| `events` | events, `dropAfter: 180 days` | each gateway | board, AI |
| `fleet_summary` | transform over `gateways` (current, undeleted rows) | refreshed by the gateways after their writes, and every minute | the home page's figures |
| `error-logs` | the platform's | `report_error` (a settings row a gateway cannot apply) | the board's toast |

One writer per table, with the two delete forms as the documented exception.
Every row has a `tsp`. Every column the code writes is declared in
data-template.yml.

## Data flows

1. **Endpoint sync** (every 10 s, needs no platform connection,
   `endpoint_sync.py`): the public VPN endpoint comes from
   `getRemoteAccessUrlForPort(51820, protocol="udp", remote_port_environment="WG_PORT")`,
   which reads the agent's live `/data/env` files. When it differs from
   wg-easy's advertised Host/Port, the companion writes it into
   `user_configs_table`, and records an `endpoint_changed` event. It also keeps
   the wg ListenPort at 51820.
2. **Registration:** once connected, the gateway writes its `gateways` row with
   `deleted: false` and its Web UI URL from `getRemoteAccessUrlForPort(51821)`
   (a development run gets its own `-dev` tunnel URL from the SDK).
3. **State** (every 30 s, sooner after a sync event, `register_device.py`):
   `vpn_state.collect()` reads wg-easy's database (read-only), `wg show`, the
   kernel and the local Web UI port, and builds the gateway's state, the client
   list and the setup checklist. The companion writes what changed: a partial
   `gateways` row, `clients` rows, `checks` rows, a batch of `traffic` rows each
   minute, and the queued `events`. After a `gateways` write it refreshes
   `fleet_summary`.
4. **Settings:** the gateway subscribes to `gateway_settings` first, then reads
   the newest row for its own `device_id`, and applies a row only when its
   `tsp` is newer than the one applied last (kept in
   `/data/.ironflock_settings_tsp`, so a restart does not re-apply an old row
   over a later Web UI edit). Applying writes the default Allowed IPs into
   wg-easy's `user_configs_table` (new clients only) and records an
   `allowed_ips_applied` event; the next `gateways` row shows the new default.
   A row it cannot use (invalid CIDR) is reported with `report_error` and an
   `events` row, and is not retried. A row that arrives before wg-easy's
   first-boot setup has finished waits until it has.
5. **Removal:** the board's delete forms write `deleted: true`. Every gateway
   follows `gateways` and refreshes `fleet_summary` when such a row arrives, so
   the home figures drop a removed gateway at once.
6. **AI tools:** `ai_tools.py` registers the `vpn.*` device functions and the
   knowledge library (`app_knowledge.*`) after the connection is up; the SDK
   restores them after a reconnect.

## Parameters, ports and tunnels

- Parameters (`env-template.yml`) are installation values, applied by wg-easy
  on the first start only: admin username and password, DNS, the first default
  Allowed IPs, the VPN subnets. `DISABLE_IPV6` and `INSECURE` apply on every
  start. What users change while the app runs is in `gateway_settings`.
- Port 51821/http (`WEB_UI_PORT` in `vpn_state.py`): the Web UI, through an
  HTTPS tunnel; its URL is `gateways.web_url`, embedded on the gateway's page.
- Port 51820/udp (`VPN_PORT`): the VPN. The tunnel assigns a public UDP port,
  forwards it to 51820 in the container and injects the number as `WG_PORT`
  (`remote_port_environment`).

## Device functions

`vpn.status`, `vpn.clients`, `vpn.diagnose`, `vpn.route_check`,
`vpn.resync_endpoint` (ai_tools.py) and `app_knowledge.list`,
`app_knowledge.get` (ironflock-knowledge-core). The topics match
`.ironflock/ai-template.yml`; `check_knowledge.py` enforces it.

## Failure behaviour

- The endpoint sync runs without the platform, so the VPN stays usable when the
  router is unreachable.
- A table write waits up to the SDK's reconnect window and then raises
  `RuntimeError`; the state loop catches it and writes on the next tick. What
  was written is remembered only after the write succeeded.
- The first state row waits up to 90 s for wg-easy, so a restart does not
  publish a transient PROBLEM.
- The companion exits on SIGTERM; `entrypoint.sh` restarts it if it dies, and
  ignores SIGHUP for it (see CLAUDE.md).
