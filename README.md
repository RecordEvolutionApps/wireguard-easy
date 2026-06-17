# Secure, Fast, and Easy Remote Access with WireGuard

WireGuard is a modern and speedy VPN that uses advanced cryptography. It's designed to be faster than OpenVPN and can be used on embedded interfaces. The WireGuard VPN App is a versatile VPN suitable for a variety of situations such as secure remote access to your edge devices.

<p align="center">
  <img src="https://raw.githubusercontent.com/WeeJeWel/wg-easy/master/assets/screenshot.png" width="802" />
</p>

## Here's what the app offers

First off, this app is just a packaging of the original great work hosted in this GitHub repository [here](https://github.com/wg-easy/wg-easy). The code for this derived app can be found [here](https://github.com/RecordEvolutionApps/wireguard-easy).

[![Build & Publish latest Image](https://github.com/wg-easy/wg-easy/actions/workflows/deploy.yml/badge.svg?branch=production)](https://github.com/wg-easy/wg-easy/actions/workflows/deploy.yml)
[![Lint](https://github.com/wg-easy/wg-easy/actions/workflows/lint.yml/badge.svg?branch=master)](https://github.com/wg-easy/wg-easy/actions/workflows/lint.yml)
[![GitHub Stars](https://img.shields.io/github/stars/wg-easy/wg-easy)](https://github.com/wg-easy/wg-easy/stargazers)
[![License](https://img.shields.io/github/license/wg-easy/wg-easy)](LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/wg-easy/wg-easy)](https://github.com/wg-easy/wg-easy/releases/latest)
[![Image Pulls](https://img.shields.io/badge/image_pulls-11M-blue)](https://github.com/wg-easy/wg-easy/pkgs/container/wg-easy)

* **Robust Security:** Our app creates a secure tunnel, shielding your connection from prying eyes on any network, including vulnerable public Wi-Fi hotspots. We employ the latest encryption protocols, including ChaCha20, Poly1305, and Curve25519, to ensure your data remains confidential and your communications private.
* **High-Speed Performance:** Experience lightning-fast browsing, streaming, and downloading. WireGuard's streamlined design minimizes overhead, delivering faster performance compared to traditional VPN protocols. This is crucial for applications like remote desktop and file transfers often used in automation.
* **Simple Setup:** Our intuitive design and user-friendly interface make it easy to establish a secure connection, which is essential for quickly accessing machines in a fast-paced industrial environment.
* **Unrestricted Access:** Bypass geo-restrictions and network limitations to access your favorite content from anywhere in the world. This also enables access to industrial equipment and networks that might be segmented or behind firewalls.
* **Privacy Protection:** Our app safeguards your online activity and protects your sensitive information.
* **Remote Access for Automation Engineers:** This app is particularly useful for automation engineers needing secure and reliable remote access to shop floor machines.  Program PLCs, download configurations, and perform diagnostics with tools like Codesys and Tia Portal, as if you were on-site.

**Key Technical Features:**

* **WireGuard Protocol:** Built on the modern and secure WireGuard VPN protocol.
* **Advanced Cryptography:** Utilizes ChaCha20 encryption, Poly1305 authentication, and Curve25519 key exchange.
* **Minimal Overhead:** Designed for speed and efficiency, minimizing latency and maximizing throughput. This is critical for real-time control and monitoring of industrial equipment.
* **Cross-Platform Compatibility:** Works seamlessly across iOS, Android, macOS, Windows, and Linux. This allows engineers to use their preferred devices, whether in the office or on the go.
* **Open Source:** Our code is publicly available for review and audit.

With our WireGuard-powered app, you get uncompromising security and blazing-fast performance.

## Requirements

An Edge Device running Linux (amd64 or arm64) with a kernel that supports WireGuard (all modern kernels).

> **Note:** wg-easy v15 no longer supports 32-bit ARM (armv6/armv7).

## First login

This app is based on **wg-easy v15**. On the first start the admin account is created automatically from the `Admin Username` / `Admin Password` parameters below, so the setup wizard is skipped and you can log straight into the Web UI. **Change the default password right after your first login.**

## Options

These options can be configured in the parameters of the app. All values below are applied **only on the first start** (while the database is still empty) — change them afterwards directly in the Web UI.

| Parameter | Default | Description |
| - | - |  - |
| Admin Username | `admin` | Initial admin username (min. 2 characters). |
| Admin Password | `wireguard1234` | Initial admin password (min. 12 characters). Change it after the first login. |
| DNS Server clients will use | `1.1.1.1` | DNS server(s) handed to clients, comma-separated. |
| Allowed IPs clients will use | `0.0.0.0/0, ::/0` | Allowed IPs for clients, comma-separated. |
| Disable IPv6 | `true` | Disable IPv6 support on the server. |

Other WireGuard settings (MTU, persistent keep-alive, client IP range, and the pre/post-up & down hooks) are no longer environment variables in v15 — they are managed in the Web UI.

## License

This project is licensed under the AGPL-3.0-only License - see the [LICENSE](LICENSE) file for details

This project is not affiliated, associated, authorized, endorsed by, or in any way officially connected with Jason A. Donenfeld, ZX2C4 or Edge Security

"WireGuard" and the "WireGuard" logo are registered trademarks of Jason A. Donenfeld