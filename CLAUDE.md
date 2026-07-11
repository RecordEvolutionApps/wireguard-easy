# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

An IronFlock (Record Evolution) edge-device app that packages the upstream [wg-easy](https://github.com/wg-easy/wg-easy) WireGuard VPN server. There is no application source code here — only integration glue: a Dockerfile extending the pinned upstream image, an entrypoint script, a device-registration script, and IronFlock platform manifests in `.ironflock/`. The app is deployed to Linux edge devices (amd64/arm64) through the IronFlock platform, which injects runtime environment variables (`DEVICE_KEY`, `WG_PORT`, user parameters from `env-template.yml`) and runs the container privileged.

## Commands

- Build: `docker build -t wireguard-easy .`
- There are no tests or linters. Verification means deploying via the IronFlock platform and reading the container logs — `entrypoint.sh` prints a startup config banner ("wg-easy startup config") for exactly this purpose.

## Architecture

`Dockerfile` extends `ghcr.io/wg-easy/wg-easy:<pinned version>` and only adds Python 3, the `ironflock` SDK (pinned in `requirements.txt`), and the two scripts under `/ironflock`. The CMD is replaced with `entrypoint.sh`, which orchestrates startup and then `exec`s the unmodified upstream server (`node /app/server/index.mjs`).

`entrypoint.sh` is plain bash (deliberately: all Python logic lives in `register_device.py`) and runs, in order:

1. Enables forwarding sysctls (`ip_forward`, `src_valid_mark`) — required once apps move to bridge networking; no-op under today's host networking.
2. Symlinks `/etc/wireguard -> /data`. wg-easy stores everything in a SQLite DB at `/etc/wireguard/wg-easy.db`, but only `/data` is a persistent volume on IronFlock devices. (`/data` also holds the agent-maintained `env/` directory, so it is never truly empty.)
3. Exports wg-easy v15 unattended-setup vars (`INIT_ENABLED`, `INIT_HOST`, `INIT_PORT`) — a best-effort first-boot seed from plain env vars (`TUNNEL_DOMAIN`, `WG_PORT`) — and prints the startup banner (password masked).
4. Launches `register_device.py` in the background (so an unreachable router can never block the VPN) and `exec`s the unmodified upstream server.

`register_device.py` is a long-lived companion process that owns all platform integration:

- Publishes the device's web UI URL (`getRemoteAccessUrlForPort(51821)`) to the IronFlock `devices` table once the WAMP connection joins the router (the dashboard in `board-template.yml` reads it; schema in `data-template.yml`). The connection closes after publishing.
- Endpoint sync loop (deliberately WAMP-independent): every 10s computes the public VPN endpoint via `getRemoteAccessUrlForPort(51820, protocol="udp", remote_port_environment="WG_PORT")` and rewrites `host`/`port` in wg-easy's `user_configs_table` when it changed. This is required because the device agent activates/deactivates tunnels and rewrites the `/data/env/*.txt` files in RUNNING containers without a restart, while wg-easy reads `INIT_*` only on first boot.

## Critical invariants

- **First-boot-only semantics:** every `INIT_*` variable (username, password, DNS, allowed IPs, host, port) is applied by wg-easy only while the DB is empty. Afterwards settings live in the DB and are changed in the Web UI — except the client-facing Host/Port, which the sync loop in `register_device.py` overwrites whenever the tunnel endpoint changes. Do not "fix" endpoint settings via the Admin UI or via `INIT_*` changes on existing installs; the sync loop owns them (an Admin UI edit is clobbered within ~10s).
- **wg-easy DB facts (verified against the v15.3.0 source and image):** every config download / QR request re-reads `user_configs_table` (single row, `id='wg0'`) from SQLite, so external UPDATEs take effect immediately without restarting the server. The server's own connection uses journal mode `delete` with `busy_timeout=0`, so external writers must keep transactions to one short UPDATE. `interfaces_table.port` is the wg ListenPort (always 51820 in-container) — never rewrite it; only `user_configs_table.host/port` (the advertised endpoint) may be synced.
- **Two distinct network paths:** the Web UI (port 51821) travels over an HTTPS tunnel subdomain; the VPN itself is UDP and cannot — clients need `Endpoint = <tunnel domain>:<public UDP port>`. Both URLs must be composed by the ironflock SDK's `getRemoteAccessUrlForPort` (never hardcode hosts or reimplement the routing): it combines the device identity, `TUNNEL_DOMAIN`, and the tunnel-assigned public UDP port `WG_PORT` (declared via `remote_port_environment` in `port-template.yml`; on appliance/instance devices `WG_PORT_CLOUD` on `CLOUD_TUNNEL_DOMAIN` wins), reading live values from the agent-maintained files in `/data/env` with start-time env vars as fallback. The public UDP port is forwarded to 51820 inside the container.
- **Persistence depends on the symlink:** the DB must physically live at `/data/wg-easy.db`. The banner warns if `/etc/wireguard` is not linked to `/data`.
- **wg-easy validation:** admin username min 2 chars, password min 12 chars — shorter values make first login fail silently.
- **Duplicated docs:** the app description exists twice — `README.md` and the markdown widget inside `.ironflock/board-template.yml`. Update both together, including the option tables.
- **Version bumps:** the upstream version is pinned only in the Dockerfile `FROM` line, but v15-specific behavior (unattended setup, INIT_* names, no 32-bit ARM) is referenced in `entrypoint.sh` comments, `README.md`, and `env-template.yml`. Check the upstream unattended-setup docs when bumping.
- The literal port numbers passed to `getRemoteAccessUrlForPort` — `51821` (web UI, `register_device.py`) and `51820` (VPN, `entrypoint.sh`) — must match the declarations in `port-template.yml`.
- `requirements.txt` must pin `ironflock` ≥ 1.5.3 — the first version with `getRemoteAccessUrlForPort` and `append_to_table`.
