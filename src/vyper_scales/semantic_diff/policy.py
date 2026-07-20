from __future__ import annotations

import tomllib
from pathlib import Path

from .models import Policy


class PolicyError(ValueError):
    pass


def _set_of_strings(value: object, field: str) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PolicyError(f"{field} must be a list of strings")
    return frozenset(value)


def load_policy(path: str | Path | None) -> Policy:
    if path is None:
        return Policy()
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    policy = raw.get("policy", {})
    if not isinstance(policy, dict):
        raise PolicyError("[policy] must be a table")
    fail_on = _set_of_strings(
        policy.get("fail_on", ["abi", "selectors", "storage", "traces"]),
        "policy.fail_on",
    )
    unknown = fail_on - {"abi", "selectors", "storage", "traces", "bytecode", "source"}
    if unknown:
        raise PolicyError(f"unsupported fail_on categories: {', '.join(sorted(unknown))}")
    ignored = _set_of_strings(
        policy.get("ignore_trace_fields", ["gas", "gas_used", "execution_time_ns"]),
        "policy.ignore_trace_fields",
    )
    require_traces = policy.get("require_traces", True)
    if not isinstance(require_traces, bool):
        raise PolicyError("policy.require_traces must be a boolean")
    return Policy(fail_on=fail_on, ignore_trace_fields=ignored, require_traces=require_traces)
