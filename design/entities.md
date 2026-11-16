# Entities

What the app deals with, and how each thing is identified. Every table, page and
form follows from this model.

| Entity | Key | Table | Written by | On the board |
|---|---|---|---|---|
| gateway: an IronFlock device running the app, with its wg-easy server | `device_id`, the device's own key (`DEVICE_KEY`) | `gateways` | the gateway, about itself; the board's delete form writes `deleted` only | list, state card, embedded Web UI, remove |
| gateway settings: what users decide per gateway (the default Allowed IPs for new clients) | `device_id` | `gateway_settings` | the board's settings form | the gateway's Settings tab |
| VPN client: a wg-easy peer (laptop, phone) configured on one gateway | `client_key` = `<device_id>-<client_id>`, with `device_id` and wg-easy's `client_id` as columns | `clients` | the gateway that has it; the board's "Remove from list" form writes `deleted` only | list across gateways, per gateway, client page, remove from list |
| check: one item of a gateway's setup checklist | `device_id` + `check_id` | `checks` | the gateway | the gateway's Checks tab |
| traffic sample: per-minute transfer rates of one client | `client_key` + `tsp` | `traffic` | the gateway | charts on the gateway's Traffic tab and the client page |
| event: what the app did or observed on a gateway | `device_id` + `tsp` (with `client_key` when it is about a client) | `events` | the gateway | home, the gateway's Events tab, the client page |

`fleet_summary` is a transform over `gateways` (counts for the home page), not
an entity.

## Relations

- A gateway has its settings (`gateway_settings.device_id`), its checks, its
  clients, its traffic and its events (`device_id` on each).
- A client belongs to one gateway (`clients.device_id`). Its traffic and its
  events carry its `client_key`.
- `device_id` holds the same number as the platform's `device_key`, which every
  row a gateway writes also carries.

## Rules the model follows

- **Gateways register themselves.** At start each gateway writes its row with
  `device_id`, `device_name`, its Web UI URL and `deleted: false`. A gateway can
  never unregister, because nothing tells a gateway that is offline from one
  that is gone, so the board has "Remove gateway" (writes `deleted: true`), and
  nothing removes a gateway automatically. Its later state rows leave `deleted`
  out and keep a removal in force; a gateway that starts the app again
  reappears. The key is `device_id`, not `device_key`, because the board's
  delete row cannot set `device_key`, and `device_name` is a plain column the
  gateway writes, so the delete row cannot clear it.
- **Clients are found by the gateway, keyed by what wg-easy reports.** wg-easy
  numbers clients per gateway, so the key prefixes the gateway's own
  (`<device_id>-<client_id>`) and identifies a client across all gateways, as
  its route `/client/<client_key>` needs. The first row about a client in a run
  of the app writes `deleted: false`; a client deleted in the Web UI gets a row
  with `deleted: true` and status `REMOVED` from its gateway. The board's
  "Remove from list" is for clients whose gateway is gone; a client that still
  exists reappears when its gateway restarts.
- **Users decide, gateways apply.** The default Allowed IPs for new clients is
  a row in `gateway_settings`, written by the board and applied by the gateway
  it names. Everything about the clients themselves stays in wg-easy's Web UI.
- **Entity tables are read live,** with `{latest: true}` and the filter on
  `deleted` (gateways and clients), never through a transform that
  deduplicates them. State rows hold the key, a `tsp` and the columns that
  changed.
