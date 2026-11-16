---
id: reference.checks_and_tables
title: "Reading the board: checklist meanings, client statuses, tables and events"
kind: reference
summary: >-
  What every setup check means and how to fix it, what the client statuses
  mean, which tables the board and the AI assistant read (gateway_registry,
  vpn_clients, gateway_checks, traffic, events) and the event kinds.
topic: diagnostics
keywords: [checks, checklist, status, ok, warning, problem, setup_pending, starting, connected, offline, never_connected, tables, gateway_registry, vpn_clients, gateway_checks, gateways, clients, traffic, events, sql, columns, meaning]
aliases: ["what does this check mean", "status meaning", "table columns", "which tables", "event kinds"]
verified: verified
---

## Overview
The companion process on each gateway writes five tables that the board shows
and the AI assistant can query with SQL; the board writes a sixth,
`gateway_settings`. Entity tables keep one row per change and are read with
the "latest" filter (the newest row per key); rows the gateway writes after
the first one hold only the key and the columns that changed, and the
platform carries the other columns over.

| Table | Key (one entity per) | Written when |
|---|---|---|
| `gateway_registry` | `device_id`, the gateway's IronFlock device key | at start (registration, with `device_name`, `web_url`, `deleted` false), then whenever a state value changes (at most every 30 s); the board's "Remove gateway" writes `deleted` true |
| `gateway_settings` | `device_id` | the board's Settings page of the gateway saves the default Allowed IPs |
| `gateway_checks` | `device_id` and `check_id` | a check's result or message changes |
| `vpn_clients` | `client_key`, `"<device_id>-<client_id>"` | a client is created, changed, removed, connects or disconnects; every 10 min while connected; `deleted` true once deleted in the Web UI |
| `traffic` | readings: client and minute | the client's counters moved during the minute |
| `events` | readings: one row per event | something happened (append-only) |

The tables `gateways`, `clients` and `checks` hold only the history of app
versions before 2026-11-16 (keyed by the platform's `device_key`, gateway name
in `devname`); nothing writes them any more. IronFlock cannot change an
existing table's entity key, so the current tables have new names.

`vpn_clients` also carries `device_id`, `device_name` (the gateway) and
`display_name` ("client · gateway"); `traffic` and `events` carry `device_id`,
`device_name` and, when about a client, `client_key`. Removed gateways and
clients have `deleted` true: leave them out of every list.

A gateway removed on the board reappears when it starts the app again.
Clients are deleted only in the Web UI: their gateway then marks them
REMOVED, also for a client deleted while the app was not running (checked
once per start). The clients of a gateway removed on the board stay listed as
last reported.

The transform `fleet_summary` adds one row of fleet-wide counts over the
current row of every gateway that is not removed: gateways reporting, OK and
needing attention, clients connected and enabled. The gateways refresh it
after writing their state; it also recomputes every minute. The board's home
page figures read it.

## Gateway status
| status | Meaning |
|---|---|
| OK | Every check passes; `status_detail` says how many enabled clients are connected |
| WARNING | The VPN works, but something needs attention (listed in `status_detail`) |
| PROBLEM | The VPN does not work as it should; `status_detail` names the failing checks |
| SETUP_PENDING | wg-easy's first-boot setup has not finished (no admin account) |
| STARTING | wg-easy has not created its database yet |

## The checks, in order
Each check assumes the ones above it pass; fix top to bottom.

| check_id | PROBLEM/WARNING means | Fix |
|---|---|---|
| db_persisted | `/etc/wireguard` is not linked to `/data`: clients would be lost on restart | Restart the app; the entrypoint creates the link. If it stays, the device has no `/data` volume |
| database | The database is not created yet or is locked right now | Wait; a persisting WARNING means wg-easy is not starting (logs) |
| setup_done | First-boot setup unfinished | Finish the wizard in the Web UI, or fix Admin Username (min. 2) / Admin Password (min. 12) and reinstall |
| interface_up | The WireGuard interface does not exist in the kernel | Logs; kernel WireGuard support; privileged container |
| listen_port | The interface listens on a port other than 51820, so the tunnel's forwarding misses it | Automatically repaired in the database; restart the app once |
| tunnel_active | No public UDP port is assigned: nobody can connect | IronFlock, device, Remote Access: switch the VPN tunnel on. A development run gets its own UDP port shortly after start |
| endpoint_synced | The advertised Host/Port differ from the tunnel | Corrected within 10 s; clients must re-download configs |
| ip_forward | IPv4 forwarding off: clients connect but reach nothing | Privileged container; see logs |
| nat_masquerade | No MASQUERADE rule: machines cannot answer | Interface device (eth0?) in the Admin Panel, restart |
| web_ui | The Web UI does not answer locally | wg-easy starting or crashed; logs |
| default_allowed_ips | New clients would not route the VPN subnet | Add the VPN subnet to the default Allowed IPs on the gateway's Settings page of the board |
| clients | No enabled client exists | Create a client |
| expired_clients | Enabled clients past their expiry date | Extend or remove the expiry |
| never_connected | Enabled clients that never completed a handshake (INFO) | Normal for new clients; otherwise check Endpoint and tunnel |

## Client status
| status | Meaning |
|---|---|
| CONNECTED | Handshake within the last 3 minutes (WireGuard re-handshakes every 2 minutes while traffic flows) |
| OFFLINE | Had a handshake since the interface came up, but not recently: device asleep, disconnected or on another network |
| NEVER_CONNECTED | No handshake since the interface came up (a gateway restart resets this) |
| DISABLED | Switched off in the Web UI |
| EXPIRED | Past its expiry date; cannot connect |
| REMOVED | Deleted in the Web UI; `deleted` is true and lists hide it |


`rx_bytes` are bytes the gateway received from the client (the client's
upload), `tx_bytes` bytes sent to the client (its download). Both reset when
the interface restarts.

## Traffic
`traffic` holds one row per client per minute with `rx_kbs` and `tx_kbs`
(kilobytes per second averaged over the interval) and the cumulative
counters. Idle clients produce no rows, so a client missing from the chart
simply transferred nothing. Raw rows are kept 90 days; downsampled
per-minute buckets one year.

## Event kinds
| kind | Level | Meaning |
|---|---|---|
| startup | info | The companion process started (app start or restart) |
| endpoint_changed | info | The advertised client Endpoint was rewritten to the tunnel's current host:port; clients must re-download |
| allowed_ips_applied | info | The default Allowed IPs saved on the gateway's Settings page was applied to the default for new clients |
| settings_rejected | warning | The default Allowed IPs saved on the board is not a list of IP addresses or CIDR networks; nothing changed |
| listen_port_repaired | warning | The stored ListenPort was reset to 51820; restart needed |
| status_changed | info/warning | The gateway status changed; the message holds old and new status and the detail |
| client_added / client_removed | info | A client was created or deleted in the Web UI |
| client_changed | info | A client's status changed (e.g. disabled, expired) |
| client_connected / client_disconnected | info | A client's handshake state crossed the 3-minute window |

## Typical SQL questions (for the AI assistant)
- Which gateways are not OK: newest row per device_id of `gateway_registry`, then
  keep those where deleted is not true and status != 'OK'.
- Which clients on gateway X are connected: newest row per client_key of
  `vpn_clients`, then keep those with device_id = X's device_id, connected, and
  deleted not true. Filter `deleted` after picking the newest row, or an
  older row of a removed entity comes back.
- The checklist of gateway X: newest row per (device_id, check_id) of
  `gateway_checks` with device_id = X's device_id.
- What default Allowed IPs users saved for gateway X and when: `gateway_settings`
  where device_id = X's device_id, ordered by tsp desc.
- When did the endpoint last change: `events` where kind = 'endpoint_changed'
  ordered by tsp desc.
- Who transferred the most data today: sum of `rx_kbs + tx_kbs` from
  `traffic` grouped by client_name for today.
