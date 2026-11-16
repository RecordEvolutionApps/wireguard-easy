---
id: guide.security
title: "Securing the gateway: passwords, two-factor login, client lifecycle, exposure"
kind: guide
summary: >-
  What is exposed where (HTTPS tunnel with IronFlock login vs raw UDP port),
  hardening the admin login with a strong password and TOTP, managing client
  lifecycle (expiry, disable, delete), per-client firewall rules, and what
  the app never does.
topic: security
keywords: [security, password, 2fa, totp, two-factor, expiry, disable, delete, firewall, exposure, public, port, access, privileges, audit, keys, rotate]
aliases: ["is this secure", "harden", "who can access", "revoke access", "two factor", "lock down"]
verified: verified
---

## Overview
Two things are reachable from the internet, and they are protected
differently:

| Path | Protection |
|---|---|
| Web UI (HTTPS tunnel subdomain) | IronFlock login and device access rights first, then wg-easy's own login. Only people with access to the device in IronFlock can even reach the login page, unless someone switches the port to Public in IronFlock |
| VPN (public UDP port) | WireGuard itself: a packet without a valid client key gets no answer at all. The port is a raw UDP tunnel without an IronFlock login in front, by design |

The public UDP port shows nothing to port scanners; WireGuard stays silent to
unauthenticated traffic. The Web UI is where the care goes.

## Admin login
1. **Change the default password** right after the first login (user menu).
   The parameter default is public knowledge; wg-easy only enforces the
   12-character minimum, not complexity.
2. **Enable two-factor authentication** (TOTP) in the user menu: wg-easy v15
   supports authenticator apps. Keep the recovery option in mind: without
   the authenticator, the admin is locked out and the only ways back are the
   `cli` inside the container (shell access on the device) or a reinstall.
3. Create **additional users** for colleagues instead of sharing the admin
   account; wg-easy v15 has user roles and each user sees their own clients.
4. **Do not switch the Web UI port to Public** in IronFlock unless you need
   access without an IronFlock account. Private is the default and keeps
   the login page off the open internet.

## Client lifecycle
- **One client per person and device.** A shared config cannot be revoked
  for one person without cutting off everyone else.
- **Expiry dates** for temporary access (service technicians, trials): the
  client stops working automatically; the board's checklist warns about
  expired clients still enabled.
- **Disable** a client to suspend access instantly; **delete** it to revoke
  permanently (the keys are gone, a new config is needed to return).
- **Rotate keys** by deleting and recreating a client when a device was lost
  or a config may have leaked. The Events tab logs `client_removed` and
  `client_added`.
- **Review the Clients tab** now and then: clients that never connected, or
  have not connected for months, are candidates for removal.

## Restricting what a client can reach
Allowed IPs on the client are a routing choice made on the laptop; a modified
config could route more. wg-easy v15.3 and later can enforce **server-side
firewall rules per client** (the interface's firewall option and the
client's firewall IPs in the Admin Panel): the gateway then drops traffic to
destinations outside the allowed set regardless of the client's config. Use
it when technicians must reach one machine and nothing else.

## What the app itself does and does not do
- The companion process only reads WireGuard state, writes the advertised
  Endpoint and the default Allowed IPs, and publishes state to the app's
  tables. It never publishes private keys, pre-shared keys or passwords.
  Client public keys appear in the `vpn_clients` table because `wg show` shows
  them; they are identifiers, not secrets.
- The Web UI URL in the `gateway_registry` table is the private HTTPS tunnel URL;
  opening it still requires an IronFlock login and the wg-easy login.
- The AI assistant's tools are read-only, except "re-sync endpoint", which
  rewrites the advertised Host/Port to the tunnel's current values. The
  assistant cannot create, change or delete clients.
- The container runs privileged (needed for the WireGuard interface and the
  sysctls); the app declares it in its data template, users grant it when
  installing or updating the app and can revoke it in the app's project
  settings (the VPN then cannot start). The app's own code does not use it for
  anything else.

## Updates
The app pins a specific wg-easy release and is updated through IronFlock's
app releases; the gateway does not phone GitHub for update checks. Security
fixes in wg-easy arrive as new app releases; install them from the App Store
or your app's release page.

## Shared responsibility
What the VPN gives access to is the machine network behind the gateway.
Segment it as you would for any remote access: the gateway should sit in the
machine network it serves, not in a flat corporate network, and machines that
must never be reached remotely should not share a subnet with those that
should.
