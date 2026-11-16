# Board

The full design of `.ironflock/board-template.yml`. The template's comment
header carries the short version; both change together.

## Brief

- **Who looks at it, where:** the engineers and IT people who run the gateways,
  at a desk or a laptop.
- **What they look for first:** whether every gateway's VPN works, and if not,
  which one and why; then who is connected right now.
- **What they change on the board:** the default Allowed IPs of a gateway (its
  Settings tab), and removing a gateway that is gone. Clients are created,
  changed and deleted in the embedded wg-easy Web UI only; the board shows
  their stats.
- **Look:** that of the wg-easy Web UI (v15, Tailwind), which the board embeds
  on every gateway page, so the two read as one app: a light `gray-50`
  (`#f9fafb`) page, white tiles with a soft shadow and an 8px radius
  (`rounded-lg shadow-md`), `gray-700` (`#374151`) text and `gray-100`
  (`#f3f4f6`) edges. wg-easy's `red-800` (`#991b1b`) marks actions only: the
  Save and delete buttons and the form accents, as in wg-easy. It never marks
  a state, so it does not compete with the alarm red. Card headings use
  wg-easy's medium weight (500). Light only: the board has one look, and
  light is what wg-easy shows unless the browser asks for dark.
- **States and colours, the same on every widget** (Tailwind 600 shades, as
  in wg-easy; idle is its `gray-500`):
  - ok `#16a34a`: gateway OK, client CONNECTED, check OK
  - warning `#d97706`: gateway WARNING or SETUP_PENDING, client NEVER_CONNECTED,
    check WARNING, event warning
  - alarm `#dc2626`: gateway PROBLEM, client EXPIRED, check PROBLEM, event error
  - idle `#6b7280`: gateway STARTING, client OFFLINE, DISABLED or REMOVED,
    check INFO, event info

## Route tree

| Route | Page | Shows | Action |
| --- | --- | --- | --- |
| `/` | Overview | the fleet figures, every gateway's state, the clients connected now, the latest events | none |
| `/gateway` | Gateways | the gateway list and the overview table | none |
| `/gateway/<device_id>` | Gateway | its state card next to the embedded wg-easy Web UI | everything about clients, in the Web UI |
| `/gateway/<device_id>/clients` | its clients | a list leading to each client's page, and the client table | none |
| `/gateway/<device_id>/traffic` | its traffic | traffic per client, last 24 hours | none |
| `/gateway/<device_id>/checks` | its checklist | the setup checklist with hints | none |
| `/gateway/<device_id>/events` | its events | what the app did and observed | none |
| `/gateway/<device_id>/settings` | its settings | the default Allowed IPs form, the saved settings | Save; "Remove gateway" |
| `/client` | Client stats | all clients on all gateways: the list and the table | none |
| `/client/<client_key>` | Client | a button to its gateway, its state card, its traffic and events | none |
| `/guide` | Guide | setup, split tunnel, troubleshooting | none |

Route segments: gateway and client `'2'`. Gateways are the project's devices,
and clients belong to them, so clients start their own branch (`/client`)
keyed by `<device_id>-<client_id>`, which is unique across gateways.

## Navigation

- A widget-navbar across the top of every page: its title "WireGuard VPN"
  leads home, its items are Gateways (`/gateway/`), Clients (`/client/`) and
  Guide (`/guide`).
- `/gateway` and every page below it: a data-driven widget-sidenav of the
  gateways (`gateway_registry`, `{latest: true}`, filter on `deleted`, route
  `device_id`). On a gateway's pages a widget-navbar is the tab bar: its title
  is the gateway's name and leads to `/gateway/<device_id>`; its items are
  Clients, Traffic, Checks, Events and Settings.
- The gateway's Clients tab has a data-driven widget-sidenav of its clients,
  each opening `/client/<client_key>` (pattern 3).
- `/client` and `/client/<client_key>`: a data-driven widget-sidenav of all
  clients (label `display_name`, "name · gateway"). On a client's page a
  widget-navbutton (the gateway's name, router icon) opens
  `/gateway/<device_id>`: a tab bar with a single item would only be a link.
- All menus pin widget-navbar and widget-sidenav 1.0.27, the button
  widget-navbutton 1.0.20.

## Pages (96 × 64 grid)

- **Overview:** the fleet card (gateways reporting, OK, needing attention;
  clients connected and enabled; from `fleet_summary`) at the top left, the
  gateway table with its coloured status beside it; below, the clients
  connected now and the latest events side by side.
- **Gateways:** the gateway list, the overview table, a short explanation.
- **Gateway:** the tab bar; a state card (status, detail, endpoint, tunnel,
  interface, subnet, defaults, client counts, last report) on the left; the
  wg-easy Web UI fills the rest.
- **Clients tab:** the gateway's client list and its client table.
- **Traffic, Checks, Events tabs:** one widget each, filling the content area.
- **Settings tab:** the settings form (prefilled with the default in force on
  the gateway), the saved settings, and the "Remove gateway" explanation with
  its red button.
- **Client stats:** the client list and the table of all clients.
- **Client:** the button to its gateway at the top; the state card; its
  traffic chart and its events beside it.
- **Guide:** one markdown page.

A widget-toast on every page shows what the gateways report with
`report_error`, in the four state colours.

The traffic chart of one client draws its two lines in greys (`#6b7280`
from the client, `#9ca3af` dashed to it), like wg-easy's own client charts.
The per-client charts of a gateway keep the chart's series colours, because
they have to tell the clients apart.

State cards show the status as text: colours in markdown would have to come
from a colour column, and the coloured status is in the tables next to it.
