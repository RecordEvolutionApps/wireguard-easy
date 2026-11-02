"""Device functions for the IronFlock AI assistant (.ironflock/ai-template.yml).

Each `topic` tool in the ai-template calls a function registered here on the
gateway the assistant picks. All of them are read-only views of this gateway
except `vpn.resync_endpoint`, which re-runs the endpoint sync. The knowledge
library (knowledge/*.md) is served by the ironflock-knowledge-core package as
`app_knowledge.list` and `app_knowledge.get`.

Handlers never raise: an exception would reach the model as an opaque WAMP
error, while a dict with an `error` key tells it how to recover. They accept
keyword arguments, one positional dict, or bare positional values, because
the agent runtime's calling convention is not pinned down. `device_key`,
which the platform adds so the assistant can address a device, is dropped.
"""

import asyncio
import functools
import inspect
import os

import endpoint_sync
import vpn_state

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge")
KNOWLEDGE_VOCAB = {"kind": {"guide", "reference"}}

CLIENT_PUBLIC_FIELDS = (
    "client_id",
    "name",
    "status",
    "enabled",
    "connected",
    "ipv4",
    "ipv6",
    "allowed_ips",
    "uses_default_allowed_ips",
    "expires_at",
    "last_handshake",
    "handshake_age_s",
    "rx_bytes",
    "tx_bytes",
)


def _params(args, kwargs, positional=()):
    out = {}
    if len(args) == 1 and isinstance(args[0], dict):
        out.update(args[0])
    else:
        for name, value in zip(positional, args):
            out[name] = value
    out.update(kwargs or {})
    out.pop("device_key", None)
    return out


def tool(positional=()):
    """Wrap an async handler into a tolerant WAMP endpoint."""

    def decorate(fn):
        allowed = set(inspect.signature(fn).parameters) - {"self"}

        @functools.wraps(fn)
        async def endpoint(self, *args, **kwargs):
            params = _params(args, kwargs, positional)
            unknown = sorted(set(params) - allowed)
            for key in unknown:
                params.pop(key)
            try:
                result = await fn(self, **params)
            except Exception as exc:  # never surface a raw error to the agent
                return {"error": f"{fn.__name__} failed: {exc}"}
            if unknown and isinstance(result, dict):
                result.setdefault("ignored_parameters", unknown)
            return result

        return endpoint

    return decorate


class VpnTools:
    """The tool handlers, bound to the SDK handle and the endpoint sync."""

    def __init__(self, flock, get_endpoint, resync):
        self.flock = flock
        self.get_endpoint = get_endpoint  # () -> (host, port) | None
        self.resync = resync  # () -> list[event]; re-runs the endpoint sync now

    async def snapshot(self) -> dict:
        return await asyncio.to_thread(vpn_state.collect, self.get_endpoint())

    @staticmethod
    def _public_client(c: dict) -> dict:
        return {k: c.get(k) for k in CLIENT_PUBLIC_FIELDS}

    @tool()
    async def status(self, detail: bool = False):
        """Gateway state, with the full checklist and client list on detail=True."""
        snap = await self.snapshot()
        checks = snap["checks"]
        out = {
            "status": snap["status"],
            "status_detail": snap["status_detail"],
            "wg_easy_version": snap["wg_easy_version"],
            "setup_done": snap["setup_done"],
            "interface": snap["interface"],
            "interface_up": snap["interface_up"],
            "listen_port": snap["listen_port"],
            "tunnel_active": snap["tunnel_active"],
            "vpn_endpoint": snap["vpn_endpoint"],
            "advertised_endpoint": f"{snap['advertised_host']}:{snap['advertised_port']}" if snap["advertised_host"] else None,
            "web_ui_url": endpoint_sync.get_web_ui_url(self.flock),
            "vpn_subnet": snap["ipv4_cidr"],
            "default_allowed_ips": snap["default_allowed_ips"],
            "default_dns": snap["default_dns"],
            "clients": {
                "total": snap["clients_total"],
                "enabled": snap["clients_enabled"],
                "connected": snap["clients_connected"],
            },
            "checks_summary": {
                level: [c["label"] for c in checks if c["result"] == level]
                for level in ("PROBLEM", "WARNING")
                if any(c["result"] == level for c in checks)
            },
            "hint": "Call diagnose for every check with its fix, clients for the client list.",
        }
        if detail:
            out["checks"] = checks
            out["clients_detail"] = [self._public_client(c) for c in snap["clients"]]
        return out

    @tool(positional=("name",))
    async def clients(self, name: str = None, include_disabled: bool = True):
        """The configured clients with their live connection state."""
        snap = await self.snapshot()
        rows = snap["clients"]
        if name:
            needle = str(name).strip().lower()
            rows = [c for c in rows if needle in c["name"].lower()]
        if not include_disabled:
            rows = [c for c in rows if c["enabled"]]
        return {
            "count": len(rows),
            "connected_window_seconds": vpn_state.CONNECTED_WINDOW_SECONDS,
            "status_meaning": {
                "CONNECTED": "handshake within the last 3 minutes",
                "OFFLINE": "connected before, no recent handshake",
                "NEVER_CONNECTED": "no handshake since the interface came up",
                "DISABLED": "switched off in the Web UI",
                "EXPIRED": "past its expiry date",
            },
            "clients": [self._public_client(c) for c in rows],
            "hint": "rx_bytes = received by the gateway from the client; tx_bytes = sent to the client. Counters reset when the interface restarts.",
        }

    @tool(positional=("client_name",))
    async def diagnose(self, client_name: str = None):
        """The setup checklist with a fix for every finding, plus one client's
        connection analysis when client_name is given."""
        snap = await self.snapshot()
        out = {
            "status": snap["status"],
            "status_detail": snap["status_detail"],
            "checks": snap["checks"],
            "order": "Fix PROBLEM results first, top to bottom: each check assumes the ones above it pass.",
        }
        if client_name:
            needle = str(client_name).strip().lower()
            client = next((c for c in snap["clients"] if c["name"].lower() == needle), None)
            if client is None:
                client = next((c for c in snap["clients"] if needle in c["name"].lower()), None)
            if client is None:
                out["client_error"] = f"No client named {client_name!r}."
                out["available_clients"] = sorted(c["name"] for c in snap["clients"])
            else:
                out["client"] = self._public_client(client)
                out["client_findings"] = self._client_findings(client, snap)
        return out

    @staticmethod
    def _client_findings(client: dict, snap: dict) -> list[str]:
        findings = []
        status = client["status"]
        if status == "DISABLED":
            findings.append("The client is disabled in the Web UI; enable it (the toggle on the client row).")
        if status == "EXPIRED":
            findings.append("The client has expired; clear or extend its expiry date in the Web UI.")
        if status == "NEVER_CONNECTED":
            findings.append(
                "No handshake ever arrived from this client. On the client device check that the tunnel is activated, "
                "and that its config carries the current Endpoint "
                f"({snap['vpn_endpoint'] or 'tunnel inactive'}); if the config was downloaded before the endpoint changed, re-download it. "
                "If the client sits in a corporate network, outbound UDP to that port may be blocked: try a mobile hotspot to confirm."
            )
        if status == "OFFLINE":
            findings.append(
                f"The last handshake was {client['handshake_age_s']} s ago. The client device is probably disconnected or asleep; "
                "a handshake reappears within seconds once it reconnects."
            )
        if status == "CONNECTED":
            findings.append("The client is connected (recent handshake). If it cannot reach a machine, check the route with route_check.")
        allowed = vpn_state.parse_list(client["allowed_ips"])
        vpn_cidr = snap.get("ipv4_cidr")
        full = any(c in ("0.0.0.0/0", "::/0") for c in allowed)
        if full:
            findings.append("Allowed IPs make this a full tunnel: all traffic, including internet, goes through the gateway.")
        elif vpn_cidr and not vpn_state._cidr_covers(allowed, vpn_cidr):
            findings.append(f"Allowed IPs do not include the VPN subnet {vpn_cidr}; add it in the Web UI and re-download the config.")
        if not snap["tunnel_active"]:
            findings.append("The gateway's VPN tunnel is inactive: no client can connect until a public UDP port is assigned.")
        if snap["status"] in ("PROBLEM", "SETUP_PENDING", "STARTING"):
            findings.append(f"The gateway itself reports {snap['status']} ({snap['status_detail']}); fix that first.")
        return findings

    @tool(positional=("client_name", "target_ip"))
    async def route_check(self, client_name: str = None, target_ip: str = None):
        """Would the client reach target_ip through the VPN, and could the gateway deliver it?"""
        if not client_name or not target_ip:
            return {"error": "client_name and target_ip are both required."}
        snap = await self.snapshot()
        return await asyncio.to_thread(vpn_state.route_check, snap, client_name, target_ip)

    @tool()
    async def resync_endpoint(self):
        """Re-run the endpoint sync now and report before/after."""
        before = await self.snapshot()
        events = await asyncio.to_thread(self.resync)
        after = await self.snapshot()
        return {
            "tunnel_endpoint": after["vpn_endpoint"],
            "advertised_before": f"{before['advertised_host']}:{before['advertised_port']}" if before["advertised_host"] else None,
            "advertised_after": f"{after['advertised_host']}:{after['advertised_port']}" if after["advertised_host"] else None,
            "changes": [e["message"] for e in events] or ["nothing to change"],
            "hint": "If the endpoint changed, clients must re-download their configs; the Endpoint line is baked into them.",
        }


TOPICS = {
    "vpn.status": "status",
    "vpn.clients": "clients",
    "vpn.diagnose": "diagnose",
    "vpn.route_check": "route_check",
    "vpn.resync_endpoint": "resync_endpoint",
}


async def register_all(flock, tools: VpnTools, log) -> list[str]:
    """Register the VPN tools and the knowledge library. Returns the topics
    that failed; never raises, so a tool outage degrades the assistant and
    nothing else."""
    failed = []
    for topic, method in TOPICS.items():
        try:
            registration = await flock.register_device_function(topic, getattr(tools, method))
        except Exception as exc:
            registration = None
            log(f"ai tools: registering {topic} failed ({exc})")
        if registration is None:
            failed.append(topic)
    log(f"ai tools: registered {len(TOPICS) - len(failed)}/{len(TOPICS)} VPN tools")

    try:
        from knowledge_core import KnowledgeLibrary, register_knowledge_tools
    except Exception as exc:
        log(f"knowledge library unavailable ({exc}); the assistant answers from general knowledge only")
        return failed + ["app_knowledge.list", "app_knowledge.get"]
    library = KnowledgeLibrary(KNOWLEDGE_DIR, vocab=KNOWLEDGE_VOCAB)
    library.load()
    for warning in library.warnings:
        log(f"knowledge doc skipped: {warning}")
        try:
            await flock.report_error(f"knowledge doc skipped: {warning}", level="warning",
                                     user_message="A guide of the VPN assistant failed to load.")
        except Exception:
            pass

    async def report(message, user_message=None):
        await flock.report_error(message, level="warning", user_message=user_message)

    failed_knowledge = await register_knowledge_tools(flock, library, report=report)
    log(f"knowledge library: {len(library.docs)} docs, tools {'registered' if not failed_knowledge else 'FAILED: ' + ', '.join(failed_knowledge)}")
    return failed + list(failed_knowledge)
