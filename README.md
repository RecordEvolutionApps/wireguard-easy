# Secure, Fast, and Easy Remote Access with WireGuard

WireGuard is a modern and speedy VPN that uses advanced cryptography. It's designed to be faster than OpenVPN and can be used on embedded interfaces. The WireGuard VPN App is a versatile VPN suitable for a variety of situations such as secure remote access to your edge devices and the machines behind them.

<p align="center">
  <img src="https://github.com/wg-easy/wg-easy/raw/master/assets/screenshot.png" width="802" />
</p>

## Here's what the app offers

First off, this app is a packaging of the original great work hosted in this GitHub repository [here](https://github.com/wg-easy/wg-easy) (wg-easy v15). The code for this derived app can be found [here](https://github.com/RecordEvolutionApps/wireguard-easy).

[![Build & Publish latest Image](https://github.com/wg-easy/wg-easy/actions/workflows/deploy.yml/badge.svg?branch=production)](https://github.com/wg-easy/wg-easy/actions/workflows/deploy.yml)
[![Lint](https://github.com/wg-easy/wg-easy/actions/workflows/lint.yml/badge.svg?branch=master)](https://github.com/wg-easy/wg-easy/actions/workflows/lint.yml)
[![GitHub Stars](https://img.shields.io/github/stars/wg-easy/wg-easy)](https://github.com/wg-easy/wg-easy/stargazers)
[![License](https://img.shields.io/github/license/wg-easy/wg-easy)](LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/wg-easy/wg-easy)](https://github.com/wg-easy/wg-easy/releases/latest)

* **Robust Security:** Our app creates a secure tunnel, shielding your connection from prying eyes on any network, including vulnerable public Wi-Fi hotspots. We employ the latest encryption protocols, including ChaCha20, Poly1305, and Curve25519, to ensure your data remains confidential and your communications private.
* **High-Speed Performance:** Experience lightning-fast browsing, streaming, and downloading. WireGuard's streamlined design minimizes overhead, delivering faster performance compared to traditional VPN protocols. This is crucial for applications like remote desktop and file transfers often used in automation.
* **Simple Setup:** The admin account is created automatically, the client endpoint follows the IronFlock tunnel by itself, and the board shows a setup checklist for every gateway.
* **Remote Access for Automation Engineers:** This app is particularly useful for automation engineers needing secure and reliable remote access to shop floor machines. Program PLCs, download configurations, and perform diagnostics with tools like Codesys and TIA Portal, as if you were on-site.
* **Fleet view on the board:** every gateway's status, the connected clients, traffic per client, a setup checklist with fixes, and an event log, for all gateways in one place.
* **AI assistant:** ask the IronFlock AI to diagnose a gateway or a client, to check whether a client reaches a machine, or how to set up a split tunnel. It runs the same checks as the board, reads the container logs and the built-in guides.
* **Open Source:** Our code is publicly available for review and audit.

**Key Technical Features:**

* **WireGuard Protocol:** Built on the modern and secure WireGuard VPN protocol.
* **Advanced Cryptography:** Utilizes ChaCha20 encryption, Poly1305 authentication, and Curve25519 key exchange.
* **Minimal Overhead:** Designed for speed and efficiency, minimizing latency and maximizing throughput. This is critical for real-time control and monitoring of industrial equipment.
* **Cross-Platform Compatibility:** Works seamlessly across iOS, Android, macOS, Windows, and Linux. This allows engineers to use their preferred devices, whether in the office or on the go.

## Requirements

An Edge Device running Linux (amd64 or arm64) with a kernel that supports WireGuard (all modern kernels).

> **Note:** wg-easy v15 no longer supports 32-bit ARM (armv6/armv7).

## Three places, three jobs

| Place | What you do there |
| - | - |
| App parameters (device or group settings) | First-boot settings: admin login, DNS, default Allowed IPs, VPN subnet |
| wg-easy Web UI (embedded on the gateway's page of the board) | Clients: create, download configs, enable, expire, delete; interface settings |
| The board | Status of every gateway, setup checklist, client connection state, traffic, events |

## First login

This app is based on **wg-easy v15**. On the first start the admin account is created automatically from the `Admin Username` / `Admin Password` parameters below, so the setup wizard is skipped and you can log straight into the Web UI. **Change the default password right after your first login.**

## Options

These options can be configured in the parameters of the app. All values below are applied **only on the first start** (while the database is still empty) — change them afterwards directly in the Web UI. Exception: **Allowed IPs clients will use** is re-applied whenever you change the parameter; it then affects newly created clients only (existing clients keep their own value — edit or recreate them in the Web UI).

| Parameter | Default | Description |
| - | - |  - |
| Admin Username | `admin` | Initial admin username (min. 2 characters). |
| Admin Password | `wireguard1234` | Initial admin password (min. 12 characters). Change it after the first login. |
| DNS Server clients will use | `1.1.1.1` | DNS server(s) handed to clients, comma-separated. |
| Allowed IPs clients will use | `0.0.0.0/0, ::/0` | Allowed IPs for new clients, comma-separated. |
| VPN IPv4 subnet | `10.8.0.0/24` | Subnet of the VPN; change it only when your network already uses 10.8.0.x. |
| VPN IPv6 subnet | `fdcc:ad94:bacf:61a4::cafe:0/112` | IPv6 subnet of the VPN (unused while IPv6 is disabled). |
| Disable IPv6 | `true` | Disable IPv6 support on the server. |
| Allow insecure HTTP access | `false` | Allow login over plain HTTP (LAN access without the tunnel). Applied on every start. |

Other WireGuard settings (MTU, persistent keep-alive, client IP range, and the pre/post-up & down hooks) are no longer environment variables in v15 — they are managed in the Web UI.

The client **Endpoint** (Host and Port under Admin Panel → Interface) is managed by the app: it always equals the public UDP endpoint of the device's IronFlock tunnel and is overwritten within seconds if edited. When it changes, the board's Events tab says so and clients must download their configs again.

## Typical use case: reach a PLC while keeping normal internet access (split tunnel)

The most common setup: this app runs on a gateway that shares a local network with a PLC (or another machine), and you want to use tools like TIA Portal or Codesys from your laptop through the VPN — while your browser and other applications keep using your normal internet connection.

That is a *split tunnel*, and you configure it per client in the WireGuard Web UI. The client's **Allowed IPs** become the `AllowedIPs` line of its downloaded config and tell your laptop which destinations are routed through the VPN — everything else stays on your normal connection.

1. Open the Web UI and create (or edit) the client for your laptop.
2. Set the client's **Allowed IPs** to the addresses that should go through the VPN. IP ranges are written in CIDR notation:
   * a single device ends in `/32`, e.g. `192.168.0.123/32` for the PLC at 192.168.0.123
   * a whole network uses a shorter suffix, e.g. `192.168.0.0/24` for all of 192.168.0.x
   * always include the VPN's own subnet `10.8.0.0/24` (the default of this app)

   Example for one PLC: `10.8.0.0/24, 192.168.0.123/32`
3. Download the client config on the laptop and connect. The setting is baked into the downloaded file — **re-download after every change**.

Traffic to those addresses now goes through the VPN; your browser and every other application keep using the laptop's normal internet connection. With `0.0.0.0/0, ::/0` as Allowed IPs you get a *full* tunnel instead: **all** laptop traffic — including web browsing — travels through the plant gateway.

Notes:

* Prefer narrow `/32` entries: if your home or office network uses the same range as the machine network (e.g. both `192.168.0.x`), a whole-subnet route conflicts with your local network.
* Connect to the PLC by its **IP address**. TIA Portal's "Accessible devices" scan (PROFINET DCP) uses Layer-2 broadcasts, which do not cross a routed VPN.
* No changes are needed on the PLC: VPN traffic is masqueraded to the gateway's own LAN address. (If your gateway's LAN interface is not `eth0`, adjust the interface device in the Web UI.)
* The app parameter *Allowed IPs clients will use* only sets the **default** for newly created clients.

## When something does not work

1. Open the gateway on the board and its **Checks** tab. The checks are ordered as a setup walk-through, each with what was observed and how to fix it: fix the first PROBLEM first.
2. **No handshake?** Check that the VPN tunnel is active (Checks), that the client's config carries the current endpoint (Events: `endpoint_changed` means re-download) and that the client's network allows outbound UDP (test from a mobile hotspot).
3. **Connected but nothing reachable?** Ping the gateway's VPN address (`10.8.0.1`); if that fails the client's Allowed IPs lack the VPN subnet. If a machine fails, its address is not in the Allowed IPs or the gateway cannot route to it.
4. **Clients lost after a restart?** The check *Database persists on /data* must be OK.
5. Ask the IronFlock AI assistant: *"Diagnose gateway X"*, *"Why does client Y not connect?"*, *"Will client Y reach 192.168.0.123?"*. It runs the checks, reads the logs and the built-in guides (getting started, architecture, split tunnel, troubleshooting, parameters, client devices, security).

## License

This project is licensed under the AGPL-3.0-only License - see the [LICENSE](LICENSE) file for details

This project is not affiliated, associated, authorized, endorsed by, or in any way officially connected with Jason A. Donenfeld, ZX2C4 or Edge Security

"WireGuard" and the "WireGuard" logo are registered trademarks of Jason A. Donenfeld
