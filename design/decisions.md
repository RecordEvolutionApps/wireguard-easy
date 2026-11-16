# Decisions

Newest first. Each entry: the date, what was decided, why, and what was left
out. Add an entry when a choice between alternatives is made; rewrite the other
documents to match, and leave the entries themselves as they were written.

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
