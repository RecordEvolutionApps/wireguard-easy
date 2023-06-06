# The WireGuard Easy App
WireGuard is a modern and speedy VPN that uses advanced cryptography. It's designed to be faster than OpenVPN and can be used on embedded interfaces. The WireGuard App is a versatile VPN suitable for a variety of situations such as secure remote access to your edge devices.

[![Build & Publish Docker Image to Docker Hub](https://github.com/WeeJeWel/wg-easy/actions/workflows/deploy.yml/badge.svg?branch=production)](https://github.com/WeeJeWel/wg-easy/actions/workflows/deploy.yml)
[![Lint](https://github.com/WeeJeWel/wg-easy/actions/workflows/lint.yml/badge.svg?branch=master)](https://github.com/WeeJeWel/wg-easy/actions/workflows/lint.yml)
[![Docker](https://img.shields.io/docker/v/weejewel/wg-easy/latest)](https://hub.docker.com/r/weejewel/wg-easy)
[![Docker](https://img.shields.io/docker/pulls/weejewel/wg-easy.svg)](https://hub.docker.com/r/weejewel/wg-easy)
[![Sponsor](https://img.shields.io/github/sponsors/weejewel)](https://github.com/sponsors/WeeJeWel)
![GitHub Stars](https://img.shields.io/github/stars/weejewel/wg-easy)

You have found the easiest way to install & manage WireGuard on any Linux host!
The original open source repository and the author can be found [here](https://github.com/WeeJeWel/wg-easy)

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
| `PASSWORD` | `admin` | `foobar123` | When set, requires a password when logging in to the Web UI. |
| `WG_MTU` | `null` | `1420` | The MTU the clients will use. Server uses default WG MTU. |
| `WG_PERSISTENT_KEEPALIVE` | `0` | `25` | Value in seconds to keep the "connection" open. If this value is 0, then connections won't be kept alive. |
| `WG_DEFAULT_ADDRESS` | `10.8.0.x` | `10.6.0.x` | Clients IP address range. |
| `WG_DEFAULT_DNS` | `1.1.1.1` | `8.8.8.8, 8.8.4.4` | DNS server clients will use. |
| `WG_ALLOWED_IPS` | `0.0.0.0/0, ::/0` | `192.168.15.0/24, 10.0.1.0/24` | Allowed IPs clients will use. |
| `WG_PRE_UP` | `...` | - | See [config.js](https://github.com/WeeJeWel/wg-easy/blob/master/src/config.js#L19) for the default value. |
| `WG_POST_UP` | `...` | `iptables ...` | See [config.js](https://github.com/WeeJeWel/wg-easy/blob/master/src/config.js#L20) for the default value. |
| `WG_PRE_DOWN` | `...` | - | See [config.js](https://github.com/WeeJeWel/wg-easy/blob/master/src/config.js#L27) for the default value. |
| `WG_POST_DOWN` | `...` | `iptables ...` | See [config.js](https://github.com/WeeJeWel/wg-easy/blob/master/src/config.js#L28) for the default value. |


## Common Use Cases

* [Using WireGuard-Easy with Pi-Hole](https://github.com/WeeJeWel/wg-easy/wiki/Using-WireGuard-Easy-with-Pi-Hole)
* [Using WireGuard-Easy with nginx/SSL](https://github.com/WeeJeWel/wg-easy/wiki/Using-WireGuard-Easy-with-nginx-SSL)

### 3. Sponsor
Are you enjoying this project? Sponsor the guys from WeeJeWel[Buy me a beer!](https://github.com/sponsors/WeeJeWel) 🍻