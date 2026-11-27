from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .matrix import generate_cases
from .models import CheckReport, Mismatch, SignaturePolicy
from .policy import fingerprint


class ResultsError(ValueError):
    pass


@dataclass(frozen=True)
class ResultDocument:
    results: tuple[dict[str, Any], ...]
    policy_fingerprint: str | None = None


def load_results(path: str | Path) -> ResultDocument:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResultsError(f"invalid JSON: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ResultsError("results are not valid UTF-8") from exc
    fingerprint_value = None
    if isinstance(raw, dict):
        if "policy_fingerprint" in raw:
            fingerprint_value = raw["policy_fingerprint"]
            if not isinstance(fingerprint_value, str) or not fingerprint_value:
                raise ResultsError("policy_fingerprint must be a non-empty string")
        values = raw.get("results")
    else:
        values = raw
    if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
        raise ResultsError("results must be an array or an object containing a results array")
    return ResultDocument(tuple(values), fingerprint_value)


def check(
    policy: SignaturePolicy, observed: tuple[dict[str, Any], ...] | ResultDocument
) -> CheckReport:
    embedded = None
    if isinstance(observed, ResultDocument):
        embedded = observed.policy_fingerprint
        observed = observed.results
    if embedded is not None and embedded != fingerprint(policy):
        raise ResultsError("results policy_fingerprint does not match the selected policy")
    expected = {case.case_id: case for case in generate_cases(policy)}
    indexed: dict[str, dict[str, Any]] = {}
    for result in observed:
        case_id = result.get("id")
        outcome = result.get("observed")
        if not isinstance(case_id, str) or not case_id or outcome not in {"accept", "reject"}:
            raise ResultsError("every result requires id and observed=accept|reject")
        if case_id in indexed:
            raise ResultsError(f"duplicate result id: {case_id}")
        indexed[case_id] = result

    missing = tuple(sorted(set(expected) - set(indexed)))
    unexpected = tuple(sorted(set(indexed) - set(expected)))
    mismatches: list[Mismatch] = []
    for case_id in sorted(set(expected) & set(indexed)):
        case = expected[case_id]
        result = indexed[case_id]
        observed_outcome = str(result["observed"])
        observed_path = str(result.get("path", ""))
        outcome_wrong = observed_outcome != case.expected
        path_wrong = bool(observed_path) and observed_path != case.verification_path
        if outcome_wrong or path_wrong:
            mismatches.append(
                Mismatch(
                    case_id=case_id,
                    expected=case.expected,
                    observed=observed_outcome,
                    expected_path=case.verification_path,
                    observed_path=observed_path,
                )
            )
    status = "FAIL" if missing or unexpected or mismatches else "PASS"
    return CheckReport(
        status=status,
        policy_fingerprint=fingerprint(policy),
        expected_cases=len(expected),
        observed_cases=len(indexed),
        missing=missing,
        unexpected=unexpected,
        mismatches=tuple(mismatches),
    )
