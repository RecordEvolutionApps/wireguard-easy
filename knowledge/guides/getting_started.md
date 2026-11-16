---
id: guide.getting_started
title: "Getting started: from install to the first connected client"
kind: guide
summary: >-
  Step-by-step setup of the WireGuard VPN app on IronFlock: install on a
  gateway, first login, create a client, connect a laptop or phone, and how
  to verify each step on the board.
topic: setup
keywords: [setup, install, first, login, start, client, connect, download, config, qr, verify, board, checklist, wizard]
aliases: ["how do I start", "first steps", "quick start", "onboarding", "new installation"]
verified: verified
---

## Overview
The app packages the open-source wg-easy server. It runs on an IronFlock
gateway device that sits in the same network as the machines you want to
reach. People connect their laptop or phone to the gateway with the WireGuard
app, and traffic to the machines travels through that encrypted tunnel.

Three places are involved, and knowing which one does what avoids most
confusion:

| Place | What you do there |
|---|---|
| App parameters (device or group settings in IronFlock) | First-boot settings: admin login, DNS, first default Allowed IPs, VPN subnet |
| wg-easy Web UI (embedded on the board's gateway page, or the app icon on the device) | Everything about clients: create, download configs, enable, expire, delete; interface settings |
| The board (the app's dashboard) | Status of every gateway, the setup checklist, who is connected, traffic, events; per gateway the default Allowed IPs for new clients (Settings) and removing a gateway that is gone |

## Step 1: install the app on the gateway
1. In IronFlock, install the app on the device (or device group) that is
   connected to the machine network. Linux amd64 or arm64; a 32-bit ARM
   device cannot run wg-easy v15.
2. Before the first start, set the parameters: **Admin Username** (at least
   2 characters) and **Admin Password** (at least 12 characters, or the first
   login fails silently). Everything else can stay at its default.
3. Start the app. The first start creates the admin account from the
   parameters and skips wg-easy's setup wizard.

A production install opens two remote-access tunnels automatically: an HTTPS
tunnel for the Web UI and a UDP tunnel for the VPN. Check them under the
device's Remote Access page in IronFlock if the checklist says the tunnel is
inactive.

## Step 2: check the board
Open the app's board. The gateway appears in the table on the home page and in
the **Gateways** list. Its status should turn **OK** within a minute. If it
shows **SETUP_PENDING**, **PROBLEM** or **WARNING**, open the gateway, then
its **Checks** tab: every check has a message and a hint saying what to do. The
checks are ordered as a walk-through; fix the first PROBLEM first.

## Step 3: log in to the Web UI
Click the gateway in the Gateways list. Its page embeds the wg-easy Web UI.
Log in with the admin username and password from the parameters, then change
the password under the user menu. Later changes to the Admin Password
parameter have no effect: the password now lives in wg-easy's database.

## Step 4: create a client
A client is one device that connects: a laptop, a phone, a service
technician's notebook. In the Web UI press the **+** button, give the client
a name (the person or device) and create it. The client gets an address in
the VPN subnet (10.8.0.2, 10.8.0.3, ...).

Decide what the client should reach:

- **Full tunnel** (default Allowed IPs `0.0.0.0/0, ::/0`): all of the laptop's
  traffic, including web browsing, goes through the gateway. Simple, but the
  laptop's internet then comes out of the plant.
- **Split tunnel**: only the machine network goes through the VPN, everything
  else uses the laptop's own connection. Set the client's Allowed IPs to the
  VPN subnet plus the machines, e.g. `10.8.0.0/24, 192.168.0.123/32`. See
  `guide.split_tunnel`.

## Step 5: connect the client device
On the client device install the WireGuard app (see `guide.client_devices`),
then either download the client's configuration file from the Web UI and
import it, or show the QR code and scan it with the phone. Activate the
tunnel.

The configuration contains the gateway's public **Endpoint** (tunnel domain
and public UDP port). The app keeps that endpoint correct automatically; if
the tunnel is ever re-assigned, the board's Events tab says so and the client
must download its config again.

## Step 6: verify
- Board, gateway page, **Clients** tab, or **Clients** in the main menu
  (all clients of all gateways): the client turns **CONNECTED** within a few
  seconds of activating the tunnel on the device. Its own page shows its
  traffic and events.
- From the client, ping the gateway's VPN address (10.8.0.1 by default), then a
  machine's address. If the gateway answers but the machine does not, the
  client's Allowed IPs or the machine's network is the issue: see
  `guide.troubleshooting`.
- Ask the IronFlock AI assistant: "Is my laptop connected to gateway X?" or
  "Why can't client Y reach 192.168.0.123?". It runs the same checks and reads
  the same tables.

## What to do when things change
| Change | What to do |
|---|---|
| A new person needs access | Create a new client; never share one config between people |
| Someone leaves | Disable or delete their client in the Web UI; the change is immediate |
| A client should reach another machine | Edit its Allowed IPs in the Web UI, then re-download the config on the device |
| The gateway was re-installed | Clients survive if `/data` persists (checklist: Database persists on /data); otherwise re-create them |
| The default Allowed IPs should change | Set it on the gateway's **Settings** page of the board; it applies to new clients only |
| A gateway is gone for good | **Remove gateway** on its Settings page; it reappears if it ever starts the app again |
