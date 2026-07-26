"""The tool registry the executor calls — pure, table-driven, deterministic.

Every tool is a plain function over synthetic fixture tables (no I/O, no
randomness, no network). These are the same functions surfaced to MCP clients
via `tools/list` / `tools/call` in `mcp.py`.
"""

from __future__ import annotations

from typing import Any

# --- synthetic fixture tables (IP-clean, invented data only) ---------------

PO_TABLE: dict[str, dict] = {
    "PO-778": {
        "amount": 4250.00,
        "vendor": "Meridian Office Supply",
        "item": "Office furniture batch 12",
    },
    "PO-780": {
        "amount": 5800.00,
        "vendor": "Atlas Industrial Parts",
        "item": "Conveyor belt assembly",
    },
    "PO-900": {
        "amount": 12300.00,
        "vendor": "Cascade Logistics",
        "item": "Warehouse racking system",
    },
}

INVOICE_TABLE: dict[str, dict] = {
    "INV-1042": {"po_id": "PO-778", "amount": 4250.00},
    "INV-1099": {"po_id": "PO-780", "amount": 6100.00},
    "INV-2200": {"po_id": "PO-900", "amount": 13100.00},
}

POLICY_TABLE: dict[str, dict] = {
    "refund_auto_approve_limit_tier2": {
        "value": "$250.00",
        "description": "Tier-2 auto-approve refund limit is $250.00.",
    },
    "pto_carryover_fy2026": {
        "value": "5 days",
        "description": "Up to 5 PTO days may carry over into FY2026.",
    },
}

REFUND_ORDERS: dict[str, dict] = {
    "ORD-5521": {"amount": 85.00, "reason": "damaged item"},
    "ORD-9001": {"amount": 4800.00, "reason": "n/a"},
    "ORD-3310": {"amount": 250.00, "reason": "wrong size"},
}

REFUND_AUTO_APPROVE_LIMIT = 250.00


class ToolError(Exception):
    """A tool call failed against its fixture table (e.g. unknown id)."""


def lookup_po(po_id: str) -> dict[str, Any]:
    """Look up a purchase order by id."""
    record = PO_TABLE.get(po_id)
    if record is None:
        raise ToolError(f"unknown PO id: {po_id}")
    return {"po_id": po_id, **record}


def lookup_invoice(invoice_id: str) -> dict[str, Any]:
    """Look up an invoice by id."""
    record = INVOICE_TABLE.get(invoice_id)
    if record is None:
        raise ToolError(f"unknown invoice id: {invoice_id}")
    return {"invoice_id": invoice_id, **record}


def compare_amounts(invoice_amount: float, po_amount: float) -> dict[str, Any]:
    """Compare an invoice amount to a PO amount."""
    diff = round(invoice_amount - po_amount, 2)
    return {
        "invoice_amount": invoice_amount,
        "po_amount": po_amount,
        "diff": diff,
        "match": diff == 0.0,
    }


def lookup_policy(policy_key: str) -> dict[str, Any]:
    """Look up a named policy value."""
    record = POLICY_TABLE.get(policy_key)
    if record is None:
        raise ToolError(f"unknown policy key: {policy_key}")
    return {"policy_key": policy_key, **record}


def lookup_refund_order(order_id: str) -> dict[str, Any]:
    """Look up a refund-eligible order by id."""
    record = REFUND_ORDERS.get(order_id)
    if record is None:
        raise ToolError(f"unknown order id: {order_id}")
    return {"order_id": order_id, **record}


def classify_request(text: str) -> dict[str, Any]:
    """Classify a free-text request into a category + priority. Table-driven keyword rules."""
    clean = (text or "").strip()
    if not clean:
        raise ToolError("missing request text")
    lowered = clean.lower()
    if "double-charged" in lowered or "duplicate" in lowered or "refund" in lowered:
        return {"category": "billing_dispute", "priority": "high"}
    if "outage" in lowered or "down" in lowered or "broken" in lowered:
        return {"category": "technical_issue", "priority": "high"}
    return {"category": "general", "priority": "medium"}


# The registry surfaced over MCP tools/list — name -> (callable, arg schema).
REGISTRY: dict[str, dict[str, Any]] = {
    "lookup_po": {
        "fn": lookup_po,
        "description": "Look up a purchase order by id.",
        "params": {"po_id": "string"},
    },
    "lookup_invoice": {
        "fn": lookup_invoice,
        "description": "Look up an invoice by id.",
        "params": {"invoice_id": "string"},
    },
    "compare_amounts": {
        "fn": compare_amounts,
        "description": "Compare an invoice amount to a PO amount.",
        "params": {"invoice_amount": "number", "po_amount": "number"},
    },
    "lookup_policy": {
        "fn": lookup_policy,
        "description": "Look up a named policy value.",
        "params": {"policy_key": "string"},
    },
    "lookup_refund_order": {
        "fn": lookup_refund_order,
        "description": "Look up a refund-eligible order by id.",
        "params": {"order_id": "string"},
    },
    "classify_request": {
        "fn": classify_request,
        "description": "Classify free-text request into category + priority.",
        "params": {"text": "string"},
    },
}


def call_tool(name: str, args: dict) -> dict[str, Any]:
    """Invoke a registered tool by name; raises ToolError / KeyError on failure."""
    entry = REGISTRY.get(name)
    if entry is None:
        raise ToolError(f"unknown tool: {name}")
    return entry["fn"](**args)
