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

| Env | Default | Example | Description |
| - | - | - | - |
| `Admin Password` | `admin` | `foobar123` | When set, requires a password when logging in to the Web UI. |
| `MTU` | `null` | `1420` | The MTU the clients will use. Server uses default WG MTU. |
| `Persistent Kepp Alive` | `0` | `25` | Value in seconds to keep the "connection" open. If this value is 0, then connections won't be kept alive. |
| `Clients IP Address Range` | `10.8.0.x` | `10.6.0.x` | Clients IP address range. |
| `DNS Server Clients will use` | `1.1.1.1` | `8.8.8.8, 8.8.4.4` | DNS server clients will use. |
| `Allowed IPs clients will use` | `0.0.0.0/0, ::/0` | `192.168.15.0/24, 10.0.1.0/24` | Allowed IPs clients will use. |
| `WireGuard pre-up command` | `...` | - | See [config.js](https://github.com/WeeJeWel/wg-easy/blob/master/src/config.js#L19) for the default value. |
| `WireGuard post-up command` | `iptables -t mangle -A PREROUTING -i wg0 -j MARK --set-mark 0x30; iptables -t nat -A POSTROUTING ! -o wg0 -m mark --mark 0x30 -j MASQUERADE; iptables -A INPUT -p udp -m udp --dport 51820 -j ACCEPT; iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT;` | `iptables ...` | See [config.js](https://github.com/WeeJeWel/wg-easy/blob/master/src/config.js#L20) for the default value. |
| `WireGuard pre-down command` | `...` | - | See [config.js](https://github.com/WeeJeWel/wg-easy/blob/master/src/config.js#L27) for the default value. |
| `WireGuard post-down command` | `...` | `iptables ...` | See [config.js](https://github.com/WeeJeWel/wg-easy/blob/master/src/config.js#L28) for the default value. |
