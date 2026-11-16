# Decisions

Newest first. Each entry: the date, what was decided, why, and what was left
out. Add an entry when a choice between alternatives is made; rewrite the other
documents to match, and leave the entries themselves as they were written.

## 2026-11-16: No client actions on the board

**Decided:** the board's "Remove from list" on a client page is gone, the
client page leads to its gateway with a widget-navbutton instead of a
one-item tab bar, and the menu item reads "Client stats". The gateway closes
clients that were deleted in wg-easy while the companion was not running: once
per run it reads the clients `vpn_clients` lists for it and writes
`deleted: true` / `REMOVED` for those wg-easy no longer has.
**Why:** clients are created, changed and deleted only in wg-easy. "Remove
from list" only hid a row on the board, the client kept working and came back
on the next restart, which read like a delete that did not work. The one real
gap it covered, a client deleted while the app was down, belongs to the
gateway, the one writer of the table.
**Left out:** hiding the clients of a gateway removed on the board. They stay
listed as last reported; a list without them needs a join with
`gateway_registry`, i.e. a transform, which would make the client lists follow
changes only on refresh.

## 2026-11-16: New tables for the re-keyed entities

**Decided:** the entity tables are `gateway_registry` (key `device_id`),
`vpn_clients` (`client_key`) and `gateway_checks` (`device_id`, `check_id`).
`gateways`, `clients` and `checks` stay in the data template exactly as
released before (keyed by `device_key`, gateway name in `devname`), and
nothing writes or reads them.
**Why:** the refactor below re-keyed those three tables in place. IronFlock
refuses to change an existing table's entity key (`maintainLatestFlagFor`),
so the platform's tables kept the old schema and the board, the gateway
sidenav first, bound to columns they do not have (`device_id`,
`device_name`, `deleted`, `client_key`). MTConnectCollector solved the same
with `gateway_registry` (collector_core 3.0.1). The template validator does
not catch a key change.
**Consequence:** the history before the refactor stays in the old tables and
is not shown on the board. Each gateway registers in `gateway_registry` on
its first start of this version.
**Left out:** copying the old rows over; they have no `device_id`, and the
gateways republish their state within a minute.

## 2026-11-16: Declare privileged access

**Decided:** `.ironflock/data-template.yml` declares `privileged:` with a
reason. IronFlock now runs a single-image app with Docker's defaults unless it
declares privileged access, and a development run is privileged only with the
declaration; the first DEV run without it failed with `RTNETLINK answers:
Operation not permitted` from `wg-quick up`. wg-easy needs `CAP_NET_ADMIN` for
the interface, the sysctls and iptables.

**Left out:** a one-service docker-compose.yml with only `cap_add: [NET_ADMIN]`
would ask for less, but it still needs the same declaration and grant, and a
Compose app loses `/data`, which the database's persistence depends on.

## 2026-11-16: Refactor to the IronFlock app guidelines

**Decided**, after a review against the ironflock-templates guidelines:

- **Entity keys are columns the gateway writes.** `gateways`, `checks` and
  `clients` were keyed by the platform's `device_key`, which a board-written
  row cannot set. They are now keyed by `device_id` (and `client_key`), and
  `gateways` has a `deleted` column with "Remove gateway" on the board. The
  tables were re-keyed in place: old rows have no `device_id` and drop out of
  the lists, and each gateway republishes its state within a minute of
  starting. Keeping the old rows visible was not needed.
- **Clients get their own branch** (`/client/<device_id>-<client_id>`)
  instead of only a tab of their gateway: users look for "who is connected"
  across all gateways, and the route guidelines start what belongs to a device
  in its own branch. The key prefixes the gateway's `device_id` because
  wg-easy numbers clients per gateway.
- **The default Allowed IPs moved from a parameter to the board.** It is the
  one setting users change while the app runs; it is now a row in
  `gateway_settings` per gateway, which the gateway follows live and applies to
  wg-easy. The `INIT_ALLOWED_IPS` parameter stays as the first-boot seed only,
  and the app no longer re-applies it when it changes (that logic and its
  state file are gone). Other first-boot values stay parameters: they are
  installation values that wg-easy owns afterwards.
- **Settings apply once, newest first.** The `tsp` of the settings row applied
  last is kept on `/data`, so a restart does not re-apply an old row over a
  later edit in the Web UI: the last writer wins, as before.
- **The home figures are a markdown card** over `fleet_summary`, which the
  gateways refresh after their writes (`refresh_transform`, ironflock 1.11)
  instead of a 10-second schedule; a one-minute schedule stays as a backstop.
  The transform now ignores removed gateways.
- **The `-dev` suffix workaround for the Web UI URL is gone**: ironflock 1.11.2
  returns a development run's own tunnel URL.
- **Look: that of the wg-easy Web UI, not a generic preset.** The board
  embeds wg-easy on every gateway page, so it takes wg-easy's grey panels,
  shadows, radius and text colour, and its `red-800` for the buttons. The
  state colours are Tailwind's, as in wg-easy, and every status value maps to
  one of them (design/board.md). wg-easy marks a connected client with its
  red, but the board does not: there red means alarm, and the brand red stays
  on actions. The IronFlock `office` preset was considered first and left out:
  it would make the board look like a different app from the one it embeds.

**Left out:** managing clients on the board (wg-easy's Web UI does it well and
owns the keys); per-client delete from wg-easy through the board.

## Earlier: the companion and its two loops

**Decided:** all platform integration lives in a background Python companion
next to the unmodified wg-easy server, with an endpoint sync loop that needs no
platform connection and a state loop that writes the tables.
**Why:** the VPN must keep working, and its endpoint must keep following the
tunnel, when the router is unreachable; wg-easy itself stays upstream code.
