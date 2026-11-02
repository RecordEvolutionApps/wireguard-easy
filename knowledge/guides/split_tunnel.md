---
id: guide.split_tunnel
title: "Reach a PLC or machine while keeping normal internet (split tunnel and Allowed IPs)"
kind: guide
summary: >-
  How Allowed IPs decide what a client sends through the VPN: full tunnel vs
  split tunnel, CIDR notation, reaching PLCs with TIA Portal or Codesys,
  overlapping subnets, and why no change is needed on the machine.
topic: routing
keywords: [split tunnel, full tunnel, allowed ips, allowedips, cidr, route, plc, machine, tia portal, codesys, siemens, subnet, 192.168, 10.8.0.0, masquerade, dcp, profinet, internet]
aliases: ["cannot reach the PLC", "route only the machine network", "all my traffic goes through the plant", "AllowedIPs", "0.0.0.0/0"]
verified: verified
---

## Overview
The most common use: the gateway shares a LAN with a PLC or another machine,
and you want to use TIA Portal, Codesys, a web HMI or a remote desktop from
your laptop through the VPN, while your browser and everything else keep
using your normal internet connection.

That is a **split tunnel**. It is configured per client, in the client's
**Allowed IPs** in the wg-easy Web UI. The value becomes the `AllowedIPs`
line of the downloaded config and tells the laptop which destinations are
routed into the tunnel. Everything else stays on the laptop's own network.

## Full tunnel vs split tunnel
| Allowed IPs on the client | Effect on the laptop |
|---|---|
| `0.0.0.0/0, ::/0` (app default) | Full tunnel: all traffic, including web browsing, goes through the gateway and leaves the plant with the gateway's internet connection |
| `10.8.0.0/24, 192.168.0.123/32` | Split tunnel: only the VPN itself and the machine 192.168.0.123 go through the VPN |
| `10.8.0.0/24, 192.168.0.0/24` | Split tunnel for the whole machine network 192.168.0.x |

Always include the VPN's own subnet (`10.8.0.0/24` by default, see the
gateway's "VPN subnet" on the board). Without it the laptop cannot reach the
gateway's VPN address, other VPN clients, or DNS served over the VPN.

## CIDR notation in one minute
- `192.168.0.123/32` is exactly one address.
- `192.168.0.0/24` is all of 192.168.0.0 to 192.168.0.255.
- `192.168.0.0/16` is all of 192.168.x.x.
- `0.0.0.0/0` is everything (IPv4); `::/0` is everything (IPv6).

Prefer the narrowest entry that works, usually `/32` per machine. Wide
entries conflict with the laptop's own network more easily (next section).

## Step by step
1. Open the gateway's Web UI from the board, create or edit the client.
2. Set **Allowed IPs** to the VPN subnet plus the machines, for example
   `10.8.0.0/24, 192.168.0.123/32`.
3. Save, then **download the client config again** on the laptop (or re-scan
   the QR code on the phone). The setting is baked into the file; the running
   client does not pick it up on its own.
4. Activate the tunnel and connect to the machine by its **IP address**.

To set the default for every client created from now on, change the app
parameter **Allowed IPs clients will use**. It affects new clients only.

## Overlapping networks
If your home or office network uses the same range as the machine network
(both `192.168.0.x` is common), a `/24` entry sends your local traffic into
the VPN too and breaks local printers, NAS and sometimes the internet. Fixes,
best first:

1. Use `/32` entries for the exact machines; the laptop then routes only
   those addresses into the VPN and the rest of 192.168.0.x stays local.
2. Change the office or home subnet, or the machine subnet, so they differ.
3. On the laptop, add a more specific local route for the devices you need
   locally (a workaround, not a fix).

Also check that the **VPN subnet** itself does not collide with a network the
laptop or the plant uses. The default `10.8.0.0/24` rarely does; if it does,
set the **VPN IPv4 subnet** parameter before the first start of a fresh
install, or change the interface's CIDR in the Admin Panel (clients get new
addresses and must download their configs again).

## PLC and engineering tool notes
- **No change on the PLC.** The gateway masquerades VPN traffic to its own LAN
  address, so the PLC answers the gateway and needs neither a default gateway
  nor a route into the VPN.
- **Connect by IP address.** TIA Portal's "Accessible devices" scan, Codesys'
  network scan and PROFINET DCP use Layer-2 broadcasts, which do not cross a
  routed VPN. Enter the PLC's address directly (TIA Portal: Online access,
  "Extended download", address of the PLC; or add it in the project).
- **Siemens S7 (ISO-on-TCP, port 102), Codesys (ports 11740 and 1217 or
  11740 and 1740 depending on version), Modbus TCP (502), OPC UA (4840) and
  web HMIs (80/443)** all work through the tunnel.
- **Some tools pick the wrong network adapter.** In TIA Portal set the PG/PC
  interface to the WireGuard adapter or to TCP/IP Auto; in Codesys select the
  gateway by IP, not by scan.
- **Slow transfers or stalls on large downloads** usually mean an MTU problem
  on a doubly tunnelled path. Lower the MTU to 1280 in the client's settings
  in the Web UI (then re-download) and see `guide.troubleshooting`.

## Reaching machines on another subnet behind the gateway
The gateway can only deliver to networks it has a route to. If the machine is
on `10.10.5.0/24` and the gateway is on `192.168.0.0/24`, the gateway itself
needs a route (via a router on its LAN) to `10.10.5.0/24`, and the machine's
network must route replies back to the gateway's address. Add
`10.10.5.0/24` (or the machine's `/32`) to the client's Allowed IPs on top of
that. The AI assistant's route check tells you whether a target is covered by
the client's Allowed IPs and whether it lies on the gateway's own LAN.

## Checking a client's routes
- Board, gateway page, Clients tab: the Allowed IPs column shows what each
  client routes through the VPN.
- Ask the AI assistant "Will client laptop-marko reach 192.168.0.123 through
  gateway X?". It answers from the client's configuration.
- On the laptop, `wg show` (or the WireGuard app's details) lists the
  AllowedIPs in force. If they differ from the Web UI, the config was not
  re-downloaded.
