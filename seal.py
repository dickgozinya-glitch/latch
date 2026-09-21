"""HMAC Seal. Portable artifact a human can forward."""

from __future__ import annotations

import hashlib
import hmac
import json


def canonical(payload: dict) -> bytes:
    body = {k: payload[k] for k in payload if k != "signature"}
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_seal(payload: dict, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical(payload), hashlib.sha256).hexdigest()


def verify_signature(payload: dict, signature: str, secret: str) -> bool:
    expected = sign_seal(payload, secret)
    return hmac.compare_digest(expected, signature or "")
