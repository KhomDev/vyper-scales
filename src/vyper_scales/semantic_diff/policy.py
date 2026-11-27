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


_FAIL_ON = {"abi", "selectors", "storage", "traces", "bytecode", "source", "compiler", "integrity"}
_POLICY_FIELDS = {"fail_on", "ignore_trace_fields", "require_traces"}


def load_policy(path: str | Path | None) -> Policy:
    if path is None:
        return Policy()
    try:
        with Path(path).open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(f"invalid TOML: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise PolicyError("policy is not valid UTF-8") from exc
    if not isinstance(raw, dict):
        raise PolicyError("policy root must be a table")
    unknown_top = set(raw) - {"policy", "version"}
    if unknown_top:
        raise PolicyError(f"unknown policy tables: {', '.join(sorted(unknown_top))}")
    if "version" in raw and raw["version"] != 1:
        raise PolicyError("policy version must be 1")
    if "policy" not in raw:
        raise PolicyError("[policy] table is required")
    policy = raw["policy"]
    if not isinstance(policy, dict):
        raise PolicyError("[policy] must be a table")
    unknown_fields = set(policy) - _POLICY_FIELDS
    if unknown_fields:
        raise PolicyError(f"unknown policy fields: {', '.join(sorted(unknown_fields))}")
    fail_on = _set_of_strings(
        policy.get("fail_on", ["abi", "selectors", "storage", "traces"]),
        "policy.fail_on",
    )
    unknown = fail_on - _FAIL_ON
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
