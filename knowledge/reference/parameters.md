---
id: reference.parameters
title: "App parameters and what they do after the first start"
kind: reference
summary: >-
  Every parameter of the app (admin login, DNS, Allowed IPs, VPN subnets,
  IPv6, insecure HTTP): its default, when it is applied, and where to change
  the setting later: the Web UI, or the board for the default Allowed IPs.
topic: parameters
keywords: [parameters, settings, environment, init, username, password, dns, allowed ips, subnet, cidr, ipv6, insecure, http, defaults, first start, change later]
aliases: ["app settings", "environment variables", "how to change the password", "change dns", "change subnet"]
verified: verified
---

## Overview
Parameters are set per device or device group in the app's settings in
IronFlock. They reach the container as environment variables. wg-easy reads
most of them only on the **first start**, while its database is still empty.
Afterwards the setting lives in the database and is changed in the Web UI.
The one setting the board manages is the default Allowed IPs for new clients:
after the first start it is set on the gateway's **Settings** page of the
board, not with the parameter.

## The parameters
| Parameter | Variable | Default | Applied | Change later in |
|---|---|---|---|---|
| Admin Username | INIT_USERNAME | `admin` | First start | Web UI, user menu (min. 2 characters) |
| Admin Password | INIT_PASSWORD | `wireguard1234` | First start | Web UI, user menu. Min. 12 characters, or the account is not created |
| DNS Server clients will use | INIT_DNS | `1.1.1.1` | First start | Admin Panel, Interface (default DNS); per client in the client's settings |
| Allowed IPs clients will use | INIT_ALLOWED_IPS | `0.0.0.0/0, ::/0` | First start | Board: the gateway's Settings page (default for new clients), or Admin Panel, Interface; per client in the client's settings |
| VPN IPv4 subnet | INIT_IPV4_CIDR | `10.8.0.0/24` | First start, only together with the IPv6 subnet | Admin Panel, Interface (clients get new addresses) |
| VPN IPv6 subnet | INIT_IPV6_CIDR | `fdcc:ad94:bacf:61a4::cafe:0/112` | First start, with the IPv4 subnet | Admin Panel, Interface |
| Disable IPv6 | DISABLE_IPV6 | `true` | Every start | The parameter |
| Allow insecure HTTP access | INSECURE | `false` | Every start | The parameter |

Set by the app, not by the user: `INIT_ENABLED=true`, `INIT_HOST` (the tunnel
domain), `INIT_PORT=51820`, and `DISABLE_VERSION_CHECK=true` (updates come
through IronFlock; the gateway does not call GitHub).

## Notes per parameter
**Admin Username / Password.** The only way to use the parameters again is a
fresh database: remove the app from the device (this deletes `/data`, clients
included) and install it with the new values. Change the password in the Web
UI right after the first login instead. wg-easy does not check complexity,
only length.

**DNS Server clients will use.** Comma-separated. With a full tunnel every DNS
query of the client goes to these servers through the VPN; a plant-internal
DNS makes machine names resolvable. Changing the default later affects new
clients; existing clients keep their own DNS unless edited.

**Allowed IPs clients will use.** The destinations a client sends through the
VPN; see `guide.split_tunnel`. The parameter seeds the default on the first
start only; changing it later has no effect. Afterwards set the default per
gateway on the board: the gateway's **Settings** page
(`/gateway/<device_id>/settings`, table `gateway_settings`). The gateway
applies a saved value within seconds, also when it was offline at the time,
and records `allowed_ips_applied` in its events. A value that is not a list
of IP addresses or CIDR networks is rejected: the event `settings_rejected`
and a message on the board say why, and the default stays as it was. Last
writer wins between the board and a Web UI edit of the default; a restart
does not re-apply an older board value. Existing clients keep their own copy;
edit or recreate them, then re-download their configs.

**VPN IPv4 / IPv6 subnet.** wg-easy requires both to be set together on the
first start. Change the IPv4 subnet only when the plant or office network
already uses `10.8.0.x`. Changing the subnet later in the Admin Panel
renumbers the clients: every client must download its config again.

**Disable IPv6.** Recommended on. With IPv6 enabled the gateway also hands out
IPv6 addresses and installs ip6tables rules; plant networks rarely route IPv6
and some kernels lack the ip6tables modules, which shows up as errors in the
log.

**Allow insecure HTTP access.** Keep off: the IronFlock HTTPS tunnel provides
TLS and wg-easy's session cookie is HTTPS-only. Turn on only for direct access
on the LAN over plain HTTP (`http://<device LAN IP>:<mapped port>`), and only on
trusted networks.

## Where the first-boot values are visible
The container log starts with a `wg-easy startup config` banner listing every
effective value (password shown as length only), whether the database already
existed (`DATA STATE = EXISTING` means INIT values are ignored) and whether
the database is persisted on `/data`.
