#!/usr/bin/env python3
"""Simulate an agent about to spend. Latch sits in front of the charge."""

from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8787"


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def main() -> None:
    mandate = call(
        "POST",
        "/v1/mandates",
        {
            "principal": "acme-finance@example.com",
            "agent_id": "ops-agent-1",
            "cap_amount": 2500,
            "currency": "USD",
            "allow_merchants": ["aws", "openai", "stripe"],
            "deny_merchants": ["unknown-gpu-broker"],
            "categories": ["compute", "model", "infra"],
        },
    )
    print("MANDATE", mandate["id"], "cap", mandate["cap_amount"])

    actions = [
        {
            "agent_id": "ops-agent-1",
            "merchant": "aws",
            "category": "compute",
            "amount": 180,
            "currency": "USD",
            "intent": "reserved instances for batch job",
        },
        {
            "agent_id": "ops-agent-1",
            "merchant": "unknown-gpu-broker",
            "category": "compute",
            "amount": 400,
            "currency": "USD",
            "intent": "spot GPUs from unlisted broker",
        },
        {
            "agent_id": "ops-agent-1",
            "merchant": "aws",
            "category": "compute",
            "amount": 1200,
            "currency": "USD",
            "intent": "large train run — needs a human",
        },
    ]
    for action in actions:
        seal = call("POST", "/v1/decisions", {"mandate_id": mandate["id"], "action": action})
        print(
            f"SEAL {seal.get('seal_id')}  {seal.get('decision'):8}  "
            f"{action['merchant']:20}  ${action['amount']:<8}  {seal.get('reason')}"
        )

    print("METER", json.dumps(call("GET", "/v1/meter"), indent=2))


if __name__ == "__main__":
    main()
