from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import asdict
from pathlib import Path

from .models import SignaturePolicy, SignaturePolicyError

__all__ = ["SignaturePolicyError", "fingerprint", "load_policy"]


def load_policy(path: str | Path) -> SignaturePolicy:
    try:
        with Path(path).open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise SignaturePolicyError(f"invalid TOML: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise SignaturePolicyError("policy is not valid UTF-8") from exc
    if raw.get("version") != 1:
        raise SignaturePolicyError("policy version must be 1")
    values = raw.get("policy", {})
    if not isinstance(values, dict):
        raise SignaturePolicyError("[policy] must be a table")
    known = {field for field in SignaturePolicy.__dataclass_fields__}
    unknown = set(values) - known
    if unknown:
        raise SignaturePolicyError(f"unknown policy fields: {', '.join(sorted(unknown))}")
    return SignaturePolicy(**values)


def fingerprint(policy: SignaturePolicy) -> str:
    encoded = json.dumps(asdict(policy), separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()
