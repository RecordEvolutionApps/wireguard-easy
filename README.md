# The WireGuard VPN App
WireGuard is a modern and speedy VPN that uses advanced cryptography. It's designed to be faster than OpenVPN and can be used on embedded interfaces. The WireGuard VPN App is a versatile VPN suitable for a variety of situations such as secure remote access to your edge devices.

[![Lint](https://github.com/WeeJeWel/wg-easy/actions/workflows/lint.yml/badge.svg?branch=master)](https://github.com/WeeJeWel/wg-easy/actions/workflows/lint.yml)
[![Docker](https://img.shields.io/docker/v/weejewel/wg-easy/latest)](https://hub.docker.com/r/weejewel/wg-easy)

You have found the easiest way to install & manage WireGuard on any Linux host!

<p align="center">
  <img src="https://raw.githubusercontent.com/WeeJeWel/wg-easy/master/assets/screenshot.png" width="802" />
</p>

## Features

- **All-in-one: WireGuard + Web UI.**
- **Easy installation, simple to use.**
- **List, create, edit, delete, enable & disable clients.**
- **Show a client's QR code.**
- **Download a client's configuration file.**
- **Statistics for which clients are connected.**
- **Tx/Rx charts for each connected client.**
- **Gravatar support.**

## Requirements
A Device with Liunx and a kernel that supports WireGuard (all modern kernels).


## Options
These options can be configured in the parameters of the app:

| Parameter | Default | Description |
| - | - |  - |
| Admin Password | `admin` | When set, requires a password when logging in to the Web UI. |
| MTU | `1420` |  The MTU the clients will use. Server uses default WireGuard MTU. |
| Persistent Kepp Alive | `0` |  Value in seconds to keep the "connection" open. If this value is 0, then connections won't be kept alive. |
| Clients IP Address Range | `10.8.0.x` |  Clients IP address range. |
| DNS Server Clients will use | `1.1.1.1` |  DNS server clients will use. |
| Allowed IPs clients will use | `0.0.0.0/0, ::/0` | Allowed IPs clients will use. |
| WireGuard pre-up command |  | Networking Know How required |
| WireGuard post-up command | `iptables -t mangle -A PREROUTING -i wg0 -j MARK --set-mark 0x30; iptables -t nat -A POSTROUTING ! -o wg0 -m mark --mark 0x30 -j MASQUERADE; iptables -A INPUT -p udp -m udp --dport 51820 -j ACCEPT; iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT;`  | Networking Know How required |
| WireGuard pre-down command |   | Networking Know How required |
| WireGuard post-down command |  | Networking Know How required |
