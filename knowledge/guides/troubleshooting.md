---
id: guide.troubleshooting
title: "Troubleshooting: symptom to cause to fix"
kind: guide
summary: >-
  Symptom-first troubleshooting for the VPN: no handshake, connected but
  nothing reachable, machine unreachable, Web UI login fails, DNS, MTU and
  slow transfers, lost clients after restart, and the checklist order.
topic: troubleshooting
keywords: [troubleshooting, handshake, not connecting, no traffic, unreachable, timeout, login, password, dns, mtu, slow, lost, restart, blocked, udp, firewall, corporate, hotspot, error]
aliases: ["vpn not working", "cannot connect", "handshake did not complete", "connected but no access", "forgot password", "clients gone"]
verified: verified
---

## Overview
Work symptom-first, and start with the board: open the gateway, then the
**Checks** tab. The checks are ordered as a setup walk-through and each one
assumes the ones above it pass, so fix the first **PROBLEM** first. The
**Events** tab explains what changed and when (endpoint changes, repairs,
clients connecting). The AI assistant runs the same checks when you ask it to
diagnose a gateway or a client.

## The gateway shows PROBLEM, SETUP_PENDING or STARTING
| Status or check | Cause | Fix |
|---|---|---|
| STARTING for more than a minute | wg-easy did not create its database | Read the container logs in IronFlock; the `wg-easy startup config` banner at the top shows the effective settings |
| SETUP_PENDING | First-boot setup did not finish, usually a password shorter than 12 characters or a username shorter than 2 | Open the Web UI: it shows the setup wizard, which you can complete by hand. Or fix the parameters and reinstall the app (this deletes `/data`) |
| Database persists on /data = PROBLEM | `/etc/wireguard` is not linked to `/data` | Restart the app; if it persists, the device's `/data` volume is missing. Clients created now would be lost on restart |
| WireGuard interface not up (setup done) | Kernel without WireGuard, or the app not running privileged | Check the logs for `wg-quick` errors. Kernels 5.6+ have WireGuard built in; older ones need the module. IronFlock runs single-container apps privileged by default |
| ListenPort is not 51820 | An older version seeded the public port as ListenPort | The app repairs the database automatically; restart the app once |
| IPv4 forwarding = PROBLEM | sysctl could not be set | The container must run privileged; check the logs for the `WARNING: failed to enable net.ipv4.ip_forward` line |
| Web UI does not answer | wg-easy crashed or is starting | Logs; a restart usually heals it |

## A client never connects (no handshake)
The client shows NEVER_CONNECTED on the board, and the WireGuard app on the
device reports no handshake or no recent handshake.

| Check | What to look at |
|---|---|
| Is the gateway's tunnel active? | Checks tab: "VPN tunnel (public UDP port)". If inactive, switch the VPN tunnel on under the device's Remote Access in IronFlock |
| Does the client config carry the current Endpoint? | Compare the `Endpoint` line in the client's config with the gateway's VPN endpoint on the board. If it differs, download the config again; the Events tab shows when it changed (`endpoint_changed`) |
| Is UDP allowed out of the client's network? | Corporate guest WiFi and some hotel networks block UDP to high ports. Test from a mobile hotspot. The VPN cannot fall back to TCP |
| Is the client enabled and not expired? | Clients tab: DISABLED or EXPIRED. Enable or extend in the Web UI |
| Was the client created on this gateway? | A config from another gateway has another Endpoint and keys |
| Time on the client device | WireGuard tolerates clock drift poorly only in extreme cases; make sure the device's clock is roughly right |

A handshake that completes and then stops ("last handshake 5 minutes ago",
OFFLINE on the board) means the device went to sleep, changed network or the
app was stopped. The client reconnects on its own when it has traffic to send.

## Connected, but nothing is reachable
The client shows CONNECTED, yet pings to the gateway or machines fail.

1. **Ping the gateway's VPN address** (10.8.0.1 by default). If it fails
   while CONNECTED, the client's Allowed IPs do not include the VPN subnet.
   Add `10.8.0.0/24`, re-download.
2. **Ping a machine.** If the gateway answers but the machine does not:
   - the client's Allowed IPs do not cover the machine (Clients tab, Allowed
     IPs column; or ask the assistant to run a route check);
   - the NAT masquerade check is WARNING: the gateway's LAN interface is not
     `eth0`. Change the interface device under Admin Panel, Interface, and
     restart the app;
   - the machine is on another subnet than the gateway and the gateway has
     no route to it (see `guide.split_tunnel`);
   - the machine's own firewall drops the gateway's address, or the machine
     only answers its own subnet (PLCs with a restrictive IP filter).
3. **Overlapping networks**: if your local network is also 192.168.0.x, a
   `/24` entry hijacks local traffic. Use `/32` entries per machine.

## Can ping the machine, but the tool cannot connect
- Engineering tools that scan the network (TIA Portal accessible devices,
  Codesys scan, PROFINET DCP) rely on broadcasts that do not cross a routed
  VPN. Enter the IP address directly.
- Large downloads stall or the connection drops: MTU. Lower the client's MTU
  in the Web UI to 1280 and re-download. The path is a tunnel inside a
  tunnel, so the default 1420 can be too large.
- Protocols that embed addresses or use UDP broadcasts (some discovery and
  licensing protocols) are not routable; use the protocol's direct-address
  mode.

## Web UI problems
| Symptom | Fix |
|---|---|
| Login fails with the parameter values right after install | The password must be at least 12 characters; with a shorter one the account was never created (SETUP_PENDING). Complete the wizard in the Web UI or reinstall with a longer password |
| Forgot the admin password | The parameter cannot reset it after the first boot. Reinstall the app on the device (deletes all clients), or open a shell on the device and use wg-easy's `cli` inside the container to reset the admin password |
| Changed Host or Port in the Admin Panel and it reverted | Expected: the app owns them, see `reference.architecture` |
| Web UI opens but is blank or refuses to log in over plain HTTP | Use the HTTPS app URL from IronFlock. Direct LAN access over HTTP needs the "Allow insecure HTTP access" parameter |
| Setup wizard appears although parameters were set | The database already existed from an earlier install with setup unfinished, or INIT values were invalid. Finish the wizard; its values persist |

## DNS through the VPN
Clients get the DNS servers from the gateway's default (parameter "DNS
Server clients will use", later Admin Panel, Interface). With a full tunnel
all DNS goes to that server through the VPN. With a split tunnel, WireGuard
on Windows and macOS still sends all DNS to the VPN's DNS server while the
tunnel is up; if plant-internal names must resolve, point the DNS at a server
reachable through the VPN (e.g. a plant DNS at 192.168.0.1) and include it in
Allowed IPs. Removing the DNS line in the client config keeps the laptop's own
DNS.

## Clients disappeared after a restart or update
The database must live on `/data` (check "Database persists on /data"). If
the check is OK and clients are gone, the app was removed and re-installed
(removal deletes `/data`), or a different device was installed. Recreate the
clients; configs on the client devices must be replaced because keys are new.

## Endpoint changed, clients cannot reconnect
The Events tab shows `endpoint_changed`. Every client must download its
config again; the old Endpoint is baked into the file. Clients that kept
their old config connect to a port that no longer forwards to this gateway.

## Reading the container logs
The log in IronFlock starts with the `wg-easy startup config` banner
(effective INIT values, password masked, DB storage and data state, and
`PYTHON CHECK`: whether the companion's Python packages import), followed
by wg-easy's own lines (`Server`, `WireGuard`, `Database`) and the
companion's lines prefixed `[ironflock]`: `launching companion`, `companion
starting`, `endpoint sync: ...`, `state: gateway row published`, `event ...`,
`ai tools: ...`. If the board shows no gateway, the first `[ironflock]` line
that is missing tells where the companion stopped. Ask the AI assistant to read the logs for you; it can.
