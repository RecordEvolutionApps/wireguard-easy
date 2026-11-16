# WireGuard VPN: design

How the WireGuard VPN app is built and why, for the people and coding agents
who change it. `README.md` in the app's root is the description for the people
who install the app; this folder is for those who develop it.

| Document | What it holds |
|---|---|
| [architecture.md](architecture.md) | The parts of the app, what runs where, every table with its kind and its one writer, the data flows, parameters, ports, device functions and the failure behaviour |
| [entities.md](entities.md) | The entity model: gateways, their settings, VPN clients, checks, traffic and events, with their keys, writers and what users do with them |
| [board.md](board.md) | The board's design: the brief, the route tree, what each page shows and offers, the look and the state colours |
| [decisions.md](decisions.md) | The design decisions, newest first, dated |

## Purpose

- **Users:** the engineers and IT people who run the plant's edge gateways and
  give technicians remote access to machines. They work at a desk or laptop.
  Technicians themselves only use the WireGuard app on their laptop or phone.
- **Goal:** give people secure remote access to the machines (PLCs, HMIs,
  servers) behind an IronFlock gateway, and show at a glance whether every
  gateway's VPN works and who is connected.
- **Value:** no port forwarding and no public IP at the plant: the VPN travels
  through the IronFlock tunnel, and the client endpoint follows the tunnel by
  itself. One board shows every gateway's state and setup checklist, who is
  connected and how much traffic flows. The AI assistant diagnoses a gateway
  or a client from the same data.
- **Not in this version:** creating, editing or deleting VPN clients on the
  board. Clients are managed in the wg-easy Web UI, which the board embeds per
  gateway. Alarms by e-mail, IPv6 routing, 32-bit ARM devices.

## Keeping this folder current

- Read these documents before changing the app.
- Every change that makes a document wrong updates it in the same change: a new
  table or column, a new entity or relation, a new page or route, a new
  parameter, port or device function, a different look.
- A decision with a reason worth keeping gets a dated entry in decisions.md.
- Describe what is, not what was: rewrite a section that no longer holds
  instead of appending a correction to it. The history is in decisions.md and
  in git.
- The knowledge docs the AI assistant serves (`knowledge/`) describe the same
  behaviour for users; keep them in step too (CLAUDE.md lists which).
