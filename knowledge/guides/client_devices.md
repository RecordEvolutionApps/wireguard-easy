---
id: guide.client_devices
title: "Connecting laptops and phones: WireGuard clients on Windows, macOS, Linux, iOS, Android"
kind: guide
summary: >-
  Installing the WireGuard app on each platform, importing the config file or
  QR code, one-time links, keeping the tunnel on, what to re-download after
  a change, and per-client settings worth knowing.
topic: clients
keywords: [client, laptop, phone, windows, macos, linux, ios, android, install, import, qr, config, one-time link, always on, on-demand, keepalive, mtu, expiry]
aliases: ["how to connect my laptop", "install wireguard", "wireguard app", "import config", "scan qr", "share the config"]
verified: verified
---

## Overview
A client is one device of one person. Create it in the gateway's Web UI,
hand the configuration to the device, activate the tunnel. The configuration
holds the device's private key, so treat it like a password and never share
one configuration between people or devices.

## Getting the configuration to the device
From the client's row in the Web UI:

- **Download** gives a `.conf` file. Import it on laptops.
- **QR code** is for phones: scan it with the WireGuard app's camera import.
- **One-time link** (the link icon) creates a short-lived URL from which the
  person downloads the config once. Use it to send access by chat or mail
  without attaching the file; the link expires and works only once.

The config contains the gateway's current `Endpoint`. After the board's
Events tab shows `endpoint_changed`, or after Allowed IPs, DNS or MTU of the
client were edited, download again and replace the config on the device.

## Windows
1. Install WireGuard from wireguard.com/install (the official MSI).
2. Open WireGuard, "Import tunnel(s) from file", pick the downloaded `.conf`.
3. Activate. The tunnel can be set to start with Windows (right-click the
   tunnel). Non-administrator users need the "limited operator UI"
   registry setting to toggle tunnels.
4. For engineering tools, check that the tool uses the WireGuard adapter or
   "TCP/IP Auto" as its network interface.

## macOS
Install WireGuard from the App Store, "Import tunnel(s) from file", activate.
"On-Demand" in the tunnel's settings connects automatically on WiFi or
Ethernet.

## Linux
Install `wireguard-tools` (Debian/Ubuntu: `apt install wireguard`). Copy the
config to `/etc/wireguard/<name>.conf` and start it with `wg-quick up <name>`;
`systemctl enable wg-quick@<name>` keeps it on across reboots. NetworkManager
can also import the file.

## iOS and Android
Install WireGuard from the App Store or Play Store, add a tunnel by scanning
the QR code shown in the Web UI, activate. Both systems offer "on-demand" or
"always-on VPN" so the tunnel comes up by itself.

## Settings per client (Web UI, client settings)
| Setting | Meaning | When to change |
|---|---|---|
| Allowed IPs | Destinations routed through the VPN | Split tunnel for machine access, see `guide.split_tunnel` |
| DNS | DNS servers the device uses while connected | Plant-internal names; or leave empty to keep the device's DNS |
| MTU | Packet size on the tunnel | Lower to 1280 when large transfers stall |
| Persistent keepalive | Sends a packet every N seconds to keep NAT mappings alive | 25 s for devices behind strict NAT or when the client must stay reachable from the gateway side |
| Expiry date | The client stops working after this date | Service technicians and temporary access |
| Enabled | Switch the client on or off without deleting it | Suspend access quickly |

Rename or delete clients freely; the change is immediate on the gateway.
Deleting is final: a new client gets new keys and the device needs the new
config.

## Verifying the connection on the device
- The WireGuard app shows "Latest handshake" a few seconds after activating.
  No handshake means the Endpoint is wrong or UDP is blocked
  (`guide.troubleshooting`).
- The board's Clients tab shows the client CONNECTED (handshake within the
  last 3 minutes), with received and sent bytes.
- Ping the gateway's VPN address (10.8.0.1 by default), then a machine.

## Several people, several devices
Create one client per device, named after person and device
(`marko-laptop`, `marko-phone`). The Clients tab and the Traffic tab then
show who is connected and how much data flows. Disable a client while the
person is on leave, delete it when they leave.
