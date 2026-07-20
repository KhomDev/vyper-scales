from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import asdict
from pathlib import Path

from .models import SignaturePolicy


class SignaturePolicyError(ValueError):
    pass


def load_policy(path: str | Path) -> SignaturePolicy:
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    if raw.get("version") != 1:
        raise SignaturePolicyError("policy version must be 1")
    values = raw.get("policy", {})
    if not isinstance(values, dict):
        raise SignaturePolicyError("[policy] must be a table")
    known = {field for field in SignaturePolicy.__dataclass_fields__}
    unknown = set(values) - known
    if unknown:
        raise SignaturePolicyError(f"unknown policy fields: {', '.join(sorted(unknown))}")
    policy = SignaturePolicy(**values)
    for name, value in asdict(policy).items():
        if name == "erc7739_mode":
            continue
        if not isinstance(value, bool):
            raise SignaturePolicyError(f"policy.{name} must be a boolean")
    if policy.erc7739_mode not in {"disabled", "optional", "required"}:
        raise SignaturePolicyError("policy.erc7739_mode must be disabled, optional, or required")
    if policy.erc6492 and not policy.erc1271:
        raise SignaturePolicyError("ERC-6492 support requires ERC-1271 support")
    if policy.erc7739_mode != "disabled" and not policy.erc1271:
        raise SignaturePolicyError("ERC-7739 mode requires ERC-1271 support")
    return policy


def fingerprint(policy: SignaturePolicy) -> str:
    encoded = json.dumps(asdict(policy), separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()
