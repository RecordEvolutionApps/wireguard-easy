"""Offline check of the AI knowledge library and the ai-template (dev/CI tool).

Validates every doc under knowledge/ (frontmatter, required keys, vocabulary,
sizes, duplicate ids) with ironflock-knowledge-core, and checks
.ironflock/ai-template.yml against the caps the platform applies and the
topics the app really registers (ai_tools.TOPICS and the knowledge library).
Exits non-zero on any error.

    python3 check_knowledge.py

knowledge_core is found either installed (pip) or as the sibling checkout
../knowledge_core, as in the other IronFlock apps.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sibling = os.path.join(os.path.dirname(HERE), "knowledge_core")
if os.path.isdir(sibling):
    sys.path.append(sibling)

import yaml  # noqa: E402

from knowledge_core import DEFAULT_TOPICS, validate_library  # noqa: E402

from ai_tools import KNOWLEDGE_DIR, KNOWLEDGE_VOCAB, TOPICS  # noqa: E402

TEMPLATE = os.path.join(HERE, ".ironflock", "ai-template.yml")
TOPIC_RE = re.compile(r"^[a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)*$")
REGISTERED_TOPICS = set(TOPICS) | set(DEFAULT_TOPICS)


def check_template():
    if not os.path.isfile(TEMPLATE):
        return [f"ai-template: {TEMPLATE} not found"]
    errors = []
    with open(TEMPLATE, encoding="utf-8") as f:
        agents = yaml.safe_load(f)
    mains = [name for name, a in agents.items() if a.get("main")]
    if len(mains) != 1:
        errors.append(f"ai-template: expected exactly one main agent, got {mains}")
    for name, agent in agents.items():
        where = f"ai-template agent {name!r}"
        prompt = agent.get("system_prompt") or ""
        if not prompt:
            errors.append(f"{where}: missing system_prompt")
        if len(prompt) > 5000:
            errors.append(f"{where}: system_prompt is {len(prompt)} chars (keep it under 5000)")
        if len(agent.get("tool_description") or "") > 2000:
            errors.append(f"{where}: tool_description exceeds 2000 chars")
        if not (1024 <= int(agent.get("max_context_tokens", 0)) <= 200000):
            errors.append(f"{where}: max_context_tokens out of range 1024-200000")
        if not (1 <= int(agent.get("max_iterations", 0)) <= 1000):
            errors.append(f"{where}: max_iterations out of range 1-1000")
        tools = agent.get("tools") or {}
        if not tools:
            errors.append(f"{where}: needs at least one tool")
        for tool_name, tool in tools.items():
            twhere = f"{where} tool {tool_name!r}"
            description = tool.get("description") or ""
            if not description:
                errors.append(f"{twhere}: missing description")
            if len(description) > 1000:
                errors.append(f"{twhere}: description is {len(description)} chars (cap 1000)")
            has_topic, has_delegate = "topic" in tool, "delegate" in tool
            if has_topic == has_delegate:
                errors.append(f"{twhere}: needs exactly one of topic/delegate")
            if has_topic and not TOPIC_RE.match(tool["topic"]):
                errors.append(f"{twhere}: topic {tool['topic']!r} fails the schema regex")
            if has_topic and tool["topic"] not in REGISTERED_TOPICS:
                errors.append(f"{twhere}: topic {tool['topic']!r} is registered by nothing (expected one of {sorted(REGISTERED_TOPICS)})")
            if has_delegate and tool["delegate"] not in agents:
                errors.append(f"{twhere}: delegate {tool['delegate']!r} is not a defined agent")
            params = tool.get("parameters") or {}
            declared = (params.get("properties") or {}).get("device_key")
            if has_topic:
                if not declared:
                    errors.append(f"{twhere}: topic tool declares no device_key parameter")
                elif declared.get("type") != "integer":
                    errors.append(f"{twhere}: device_key must be type integer")
            elif declared:
                errors.append(f"{twhere}: delegate tool must not declare device_key")
    return errors


def main():
    errors, warnings = validate_library(KNOWLEDGE_DIR, vocab=KNOWLEDGE_VOCAB)
    errors.extend(check_template())
    for warning in warnings:
        print(f"WARN  {warning}")
    for error in errors:
        print(f"ERROR {error}")
    if errors:
        print(f"\n{len(errors)} error(s).")
        return 1
    print("OK - knowledge library and ai-template pass all checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
