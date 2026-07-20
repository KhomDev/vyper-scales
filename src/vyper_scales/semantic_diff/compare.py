from __future__ import annotations

from typing import Any

from .models import Artifact, Difference, DiffReport, Policy


def _abi_type(parameter: dict[str, Any]) -> str:
    value = str(parameter.get("type", ""))
    if value.startswith("tuple"):
        suffix = value[5:]
        components = parameter.get("components", [])
        if isinstance(components, list):
            return f"({','.join(_abi_type(item) for item in components)}){suffix}"
    return value


def _abi_index(abi: tuple[dict[str, Any], ...]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in abi:
        kind = str(item.get("type", "function"))
        name = str(item.get("name", kind))
        inputs = item.get("inputs", [])
        signature = f"{name}({','.join(_abi_type(value) for value in inputs)})"
        key = f"{kind}:{signature}"
        indexed[key] = {
            "stateMutability": item.get("stateMutability", ""),
            "outputs": [_abi_type(value) for value in item.get("outputs", [])],
            "anonymous": item.get("anonymous", False),
        }
    return indexed


def _clean_trace(value: Any, ignored: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean_trace(item, ignored)
            for key, item in sorted(value.items())
            if key not in ignored
        }
    if isinstance(value, list):
        return [_clean_trace(item, ignored) for item in value]
    return value


def _trace_index(traces: tuple[dict[str, Any], ...], ignored: frozenset[str]) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    for trace in traces:
        case = trace.get("case")
        if not isinstance(case, str) or not case:
            raise ValueError("every trace requires a non-empty case string")
        if case in indexed:
            raise ValueError(f"duplicate trace case: {case}")
        indexed[case] = _clean_trace(trace, ignored)
    return indexed


def _mapping_differences(
    category: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    severity: str,
) -> list[Difference]:
    differences: list[Difference] = []
    for key in sorted(set(baseline) | set(candidate)):
        left = baseline.get(key, "<missing>")
        right = candidate.get(key, "<missing>")
        if left != right:
            differences.append(Difference(category, key, severity, left, right))
    return differences


def compare(baseline: Artifact, candidate: Artifact, policy: Policy | None = None) -> DiffReport:
    policy = policy or Policy()
    differences: list[Difference] = []
    differences.extend(
        _mapping_differences(
            "abi",
            _abi_index(baseline.abi),
            _abi_index(candidate.abi),
            "breaking",
        )
    )
    differences.extend(
        _mapping_differences(
            "selectors",
            baseline.method_identifiers,
            candidate.method_identifiers,
            "breaking",
        )
    )
    if baseline.storage_layout != candidate.storage_layout:
        differences.append(
            Difference(
                "storage",
                "layout",
                "breaking",
                baseline.storage_layout,
                candidate.storage_layout,
            )
        )
    if baseline.bytecode_runtime != candidate.bytecode_runtime:
        differences.append(
            Difference(
                "bytecode",
                "runtime",
                "informational",
                baseline.bytecode_runtime,
                candidate.bytecode_runtime,
            )
        )
    if baseline.source != candidate.source:
        differences.append(
            Difference("source", "metadata", "informational", baseline.source, candidate.source)
        )

    baseline_traces = _trace_index(baseline.traces, policy.ignore_trace_fields)
    candidate_traces = _trace_index(candidate.traces, policy.ignore_trace_fields)
    trace_cases = tuple(sorted(set(baseline_traces) | set(candidate_traces)))
    if not baseline_traces and not candidate_traces:
        behavior_status = "UNASSESSED"
    else:
        trace_differences = _mapping_differences(
            "traces", baseline_traces, candidate_traces, "semantic"
        )
        differences.extend(trace_differences)
        behavior_status = "FAIL" if trace_differences else "PASS"

    failing = [difference for difference in differences if difference.category in policy.fail_on]
    if failing:
        status = "FAIL"
    elif behavior_status == "UNASSESSED" and policy.require_traces:
        status = "UNASSESSED"
    else:
        status = "PASS"

    notes: list[str] = []
    if behavior_status == "UNASSESSED":
        notes.append("no execution traces were present on either side")
    if any(difference.category == "bytecode" for difference in differences):
        notes.append("runtime bytecode changed; informational unless policy fails on bytecode")
    return DiffReport(
        status=status,
        baseline=baseline.path,
        candidate=candidate.path,
        behavior_status=behavior_status,
        differences=tuple(differences),
        compared_trace_cases=trace_cases,
        notes=tuple(notes),
    )
