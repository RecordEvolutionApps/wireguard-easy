---
id: reference.architecture
title: "How the app is wired on IronFlock: tunnels, endpoint sync, persistence"
kind: reference
summary: >-
  The two network paths (HTTPS tunnel for the Web UI, UDP tunnel for the VPN),
  why the client Endpoint is managed by the app, the ListenPort 51820 rule,
  first-boot-only settings, the board's settings, persistence and what the
  companion process does.
topic: architecture
keywords: [architecture, tunnel, endpoint, listenport, 51820, 51821, udp, https, sync, persistence, data, database, first boot, init, companion, how it works]
aliases: ["how does it work", "endpoint keeps changing", "why 51820", "host and port overwritten", "internals"]
verified: verified
---

## Overview
Inside the container two processes run: the unmodified wg-easy server
(Web UI on port 51821, WireGuard on UDP 51820) and a small companion process
from IronFlock. The companion never changes how WireGuard works; it only
keeps a few database values in step with the platform and the board, and
publishes state for the board and the AI assistant.

## Two network paths
```text
browser ──HTTPS──▶ IronFlock tunnel ──▶ container port 51821  (Web UI)
laptop  ──UDP────▶ IronFlock tunnel ──▶ container port 51820  (WireGuard)
```
- The **Web UI** travels over an HTTPS tunnel with a subdomain per device. It
  is private: only IronFlock users with access to the device can open it, and
  wg-easy asks for its own login on top.
- The **VPN** is UDP and cannot use the HTTPS subdomain. The platform assigns
  the device a **public UDP port** on the tunnel domain and forwards it to port
  51820 inside the container. Clients need exactly that `host:port` as their
  `Endpoint`.

Both URLs are composed by the IronFlock SDK from the device identity, the
tunnel domain and the assigned public port. On an appliance or private cloud
the cloud-forwarded domain and port are used when available.

## Why the app owns Host and Port
wg-easy stores the advertised client endpoint (Admin Panel, Interface: Host
and Port) in its database and bakes it into every downloaded config and QR
code. On IronFlock the public UDP port is assigned by the tunnel and can
change: when the tunnel is switched off and on, when the device is
re-installed, or when a device first gets its tunnel after the app already
runs. The device agent updates the running container's environment files
without a restart.

So every 10 seconds the companion compares the tunnel's current endpoint with
the stored Host/Port and rewrites them when they differ. wg-easy reads these
values from the database on every download, so the next config is correct at
once. Consequences:

- **Do not edit Host or Port in the Admin Panel.** They are overwritten within
  seconds. The board's Events tab records every change (`endpoint_changed`).
- **Configs downloaded before a change carry the old endpoint.** Clients must
  download again. Nothing else in the config changes.
- While the tunnel is inactive the last known endpoint is kept, so existing
  clients reconnect as soon as the tunnel is back on the same port.

## ListenPort must stay 51820
The tunnel always forwards the public port to **51820** in the container.
wg-easy's first-boot setup writes the `INIT_PORT` value into both the
advertised Port and the interface's ListenPort, which is why the app seeds
`INIT_PORT=51820` and never the public port. If the ListenPort is ever found
different (an older version of this app seeded it wrongly), the companion
repairs it in the database and logs `listen_port_repaired`; the interface
picks it up on the next restart of the app. The Checks tab shows `ListenPort
is 51820`.

## Settings that apply on the first boot only
wg-easy reads its `INIT_*` variables only while the database is empty
(`setup_step` not yet 0). Afterwards the values live in the database and are
changed in the Web UI. The app parameters map to them:

| Parameter | Variable | After the first boot |
|---|---|---|
| Admin Username, Admin Password | INIT_USERNAME, INIT_PASSWORD | Change in the Web UI (user menu) |
| DNS Server clients will use | INIT_DNS | Admin Panel, Interface |
| VPN IPv4/IPv6 subnet | INIT_IPV4_CIDR, INIT_IPV6_CIDR | Admin Panel, Interface (changes client addresses) |
| Allowed IPs clients will use | INIT_ALLOWED_IPS | Board: the gateway's Settings page; see below |
| Disable IPv6, Allow insecure HTTP | DISABLE_IPV6, INSECURE | Runtime settings, applied on every start |

**The default Allowed IPs is set on the board.** After the first start,
users change the default Allowed IPs for new clients on the gateway's
**Settings** page of the board, which saves a row in the table
`gateway_settings` for that gateway. The companion follows the table: it
subscribes, reads the newest row for its own gateway at start, and applies a
row only when it is newer than the one it applied last (recorded in `/data`).
Applying writes the value into wg-easy's default Allowed IPs and logs
`allowed_ips_applied`; a row saved while setup is still running waits until
it has finished. A value that is not a list of IP addresses or CIDR networks
is rejected (`settings_rejected` event and a message on the board) and not
retried. Last writer wins: a Web UI edit of the default persists until the
next save on the board, and a restart does not re-apply an older board value.
Existing clients are never touched; wg-easy copies the default into each
client when it is created. The `INIT_ALLOWED_IPS` parameter only seeds the
default on the first start.

## Persistence
wg-easy keeps everything, clients and keys included, in one SQLite file at
`/etc/wireguard/wg-easy.db`. On IronFlock only `/data` survives restarts and
updates, so the entrypoint links `/etc/wireguard` to `/data`, and the file
physically lives at `/data/wg-easy.db`. The check `Database persists on /data`
confirms the link. Removing the app from a device deletes `/data` and with it
all clients.

## Forwarding and NAT
The entrypoint enables `net.ipv4.ip_forward` and `src_valid_mark` in the
container's network namespace (the container runs privileged). wg-easy's
PostUp hook installs an iptables MASQUERADE rule from the VPN subnet to the
gateway's LAN interface (default `eth0`). With that, a machine on the LAN sees
VPN traffic as coming from the gateway's own address and needs no route back
into the VPN. If the gateway's LAN interface has another name, change the
interface device in the Admin Panel and restart the app.

## The companion process
`register_device.py` and its modules run next to the server for the whole
container lifetime and:

1. run the endpoint sync described above, independently of the platform
   connection, so a gateway in a restrictive network keeps a correct endpoint;
2. register the gateway at start in the table `gateways` (its device key as
   `device_id`, its name and its Web UI URL), which also brings back a
   gateway that was removed on the board;
3. apply the default Allowed IPs saved on the board, as described above;
4. every 30 s collect the gateway's state from the database, `wg show`, the
   kernel and the local Web UI port, and write what changed to the tables
   `gateways`, `clients`, `checks`, `events`, plus `traffic` every minute;
5. register the AI assistant's tools on the device: status, clients,
   diagnose, route check, endpoint re-sync and this knowledge library.

The container logs start with a `wg-easy startup config` banner that shows
the effective first-boot values (password masked), the persistence check and
whether the database already existed.
