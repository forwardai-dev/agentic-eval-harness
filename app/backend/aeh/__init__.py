"""aeh-mcp — Agentic Eval Harness over MCP.

A planner -> executor -> critic multi-agent workflow, exposed as an MCP tool,
wrapped in an offline eval + observability harness with signed, tamper-evident
evidence. Fully offline and deterministic: no API keys, no network calls.

Adapted from the deterministic-mock / hash-chained-evidence pattern proven in
Sanju Goswami's Agent Assurance Harness (AAH) — same canonical-bytes -> sha256
-> Ed25519 signing chain, applied to a new agentic workflow + MCP surface.
"""

from __future__ import annotations

__version__ = "0.1.0"
