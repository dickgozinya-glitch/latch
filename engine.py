"""Deterministic policy. The model does not vote."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from typing import Any

from seal import sign_seal, verify_signature

SECRET = os.environ.get("LATCH_SECRET", "dev-only-change-me")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mandates (
            id TEXT PRIMARY KEY,
            principal TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            currency TEXT NOT NULL,
            cap_amount REAL NOT NULL,
            remaining REAL NOT NULL,
            allow_merchants TEXT NOT NULL,
            deny_merchants TEXT NOT NULL,
            categories TEXT NOT NULL,
            valid_from INTEGER NOT NULL,
            valid_until INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS seals (
            id TEXT PRIMARY KEY,
            mandate_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            reason TEXT NOT NULL,
            action TEXT NOT NULL,
            payload TEXT NOT NULL,
            signature TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()


def _now() -> int:
    return int(time.time())


def _list(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, str):
        return [val]
    return [str(x) for x in val]


def insert_mandate(conn: sqlite3.Connection, body: dict) -> dict:
    required = ("principal", "agent_id", "cap_amount")
    missing = [k for k in required if body.get(k) in (None, "")]
    if missing:
        raise ValueError(f"missing: {', '.join(missing)}")
    mid = body.get("id") or "man_" + secrets.token_hex(8)
    now = _now()
    row = {
        "id": mid,
        "principal": str(body["principal"]),
        "agent_id": str(body["agent_id"]),
        "currency": str(body.get("currency") or "USD"),
        "cap_amount": float(body["cap_amount"]),
        "remaining": float(body.get("remaining", body["cap_amount"])),
        "allow_merchants": json.dumps(_list(body.get("allow_merchants"))),
        "deny_merchants": json.dumps(_list(body.get("deny_merchants"))),
        "categories": json.dumps(_list(body.get("categories"))),
        "valid_from": int(body.get("valid_from") or now),
        "valid_until": int(body.get("valid_until") or now + 30 * 86400),
        "status": "active",
        "created_at": now,
    }
    conn.execute(
        """INSERT INTO mandates
        (id, principal, agent_id, currency, cap_amount, remaining,
         allow_merchants, deny_merchants, categories, valid_from, valid_until, status, created_at)
        VALUES (:id,:principal,:agent_id,:currency,:cap_amount,:remaining,
                :allow_merchants,:deny_merchants,:categories,:valid_from,:valid_until,:status,:created_at)""",
        row,
    )
    conn.commit()
    return load_mandate(conn, mid)


def load_mandate(conn: sqlite3.Connection, mid: str) -> dict | None:
    cur = conn.execute("SELECT * FROM mandates WHERE id = ?", (mid,))
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    for k in ("allow_merchants", "deny_merchants", "categories"):
        d[k] = json.loads(d[k])
    return d


def load_seal(conn: sqlite3.Connection, sid: str) -> dict | None:
    cur = conn.execute("SELECT * FROM seals WHERE id = ?", (sid,))
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["action"] = json.loads(d["action"])
    return d


def meter(conn: sqlite3.Connection) -> dict:
    cur = conn.execute(
        "SELECT decision, COUNT(*) AS n FROM seals GROUP BY decision"
    )
    counts = {r["decision"]: r["n"] for r in cur.fetchall()}
    total = sum(counts.values())
    billable = total
    return {
        "decisions": total,
        "by_decision": counts,
        "suggested_invoice_usd": round(3000 + 0.05 * billable, 2),
        "note": "Monthly floor $3,000 against $0.05 per decision. Change when a controller is on the phone.",
    }


def decide(conn: sqlite3.Connection, body: dict) -> dict:
    mandate_id = body.get("mandate_id")
    action = body.get("action") or {}
    if not mandate_id:
        raise ValueError("missing: mandate_id")
    mandate = load_mandate(conn, mandate_id)
    if not mandate:
        raise ValueError("mandate_not_found")

    agent_id = str(action.get("agent_id") or body.get("agent_id") or "")
    merchant = str(action.get("merchant") or "").lower()
    category = str(action.get("category") or "").lower()
    amount = float(action.get("amount") or 0)
    currency = str(action.get("currency") or mandate["currency"])
    now = _now()

    decision = "allow"
    reason = "within_mandate"

    if mandate["status"] != "active":
        decision, reason = "deny", "mandate_inactive"
    elif now < mandate["valid_from"] or now > mandate["valid_until"]:
        decision, reason = "deny", "mandate_expired"
    elif agent_id and agent_id != mandate["agent_id"]:
        decision, reason = "deny", "agent_mismatch"
    elif currency != mandate["currency"]:
        decision, reason = "deny", "currency_mismatch"
    elif amount <= 0:
        decision, reason = "deny", "invalid_amount"
    elif merchant and merchant in [m.lower() for m in mandate["deny_merchants"]]:
        decision, reason = "deny", "merchant_denied"
    elif mandate["allow_merchants"] and merchant not in [m.lower() for m in mandate["allow_merchants"]]:
        decision, reason = "deny", "merchant_not_allowlisted"
    elif mandate["categories"] and category and category not in [c.lower() for c in mandate["categories"]]:
        decision, reason = "deny", "category_not_allowed"
    elif amount > mandate["remaining"]:
        decision, reason = "deny", "cap_exceeded"
    elif amount > mandate["cap_amount"] * 0.4:
        decision, reason = "escalate", "amount_requires_human"

    if decision == "allow":
        conn.execute(
            "UPDATE mandates SET remaining = remaining - ? WHERE id = ?",
            (amount, mandate_id),
        )

    seal_id = "sel_" + secrets.token_hex(8)
    action_record = {
        "agent_id": agent_id or mandate["agent_id"],
        "merchant": merchant,
        "category": category,
        "amount": amount,
        "currency": currency,
        "intent": action.get("intent") or "",
    }
    payload = {
        "seal_id": seal_id,
        "mandate_id": mandate_id,
        "principal": mandate["principal"],
        "decision": decision,
        "reason": reason,
        "action": action_record,
        "created_at": now,
    }
    signature = sign_seal(payload, SECRET)
    conn.execute(
        """INSERT INTO seals (id, mandate_id, decision, reason, action, payload, signature, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            seal_id,
            mandate_id,
            decision,
            reason,
            json.dumps(action_record),
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
            signature,
            now,
        ),
    )
    conn.commit()
    payload["signature"] = signature
    payload["remaining_after"] = load_mandate(conn, mandate_id)["remaining"]
    return payload


def verify_seal(conn: sqlite3.Connection, sid: str) -> dict:
    row = load_seal(conn, sid)
    if not row:
        return {"valid": False, "error": "seal_not_found"}
    payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row
    ok = verify_signature(payload, row["signature"], SECRET)
    return {"valid": ok, "seal": row}
