from __future__ import annotations

from typing import Any

from .artifact import ArtifactError
from .models import Artifact, Difference, DiffReport, Policy

_MISSING = object()


def _abi_type(parameter: object) -> str:
    if not isinstance(parameter, dict):
        raise ArtifactError("ABI parameter must be an object")
    if not isinstance(parameter.get("type"), str):
        raise ArtifactError("ABI parameter requires a string type")
    value = parameter["type"]
    if value.startswith("tuple"):
        suffix = value[5:]
        components = parameter.get("components")
        if not isinstance(components, list):
            raise ArtifactError("tuple ABI parameters require components")
        return f"({','.join(_abi_type(item) for item in components)}){suffix}"
    return value


def _event_indexed(parameter: dict[str, Any]) -> bool:
    indexed = parameter.get("indexed", False)
    if not isinstance(indexed, bool):
        raise ArtifactError("event indexed flag must be a boolean")
    return indexed


def _abi_index(abi: tuple[dict[str, Any], ...]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in abi:
        if not isinstance(item, dict):
            raise ArtifactError("ABI entries must be objects")
        kind = item.get("type", "function")
        if not isinstance(kind, str) or not kind:
            raise ArtifactError("ABI entry type must be a string")
        name = item.get("name", kind)
        if not isinstance(name, str):
            raise ArtifactError("ABI entry name must be a string")
        inputs = item.get("inputs", [])
        outputs = item.get("outputs", [])
        if not isinstance(inputs, list) or not isinstance(outputs, list):
            raise ArtifactError("ABI inputs and outputs must be arrays")
        signature = f"{name}({','.join(_abi_type(value) for value in inputs)})"
        key = f"{kind}:{signature}"
        if key in indexed:
            raise ArtifactError(f"duplicate ABI entry: {key}")
        mutability = item.get("stateMutability", "")
        anonymous = item.get("anonymous", False)
        if not isinstance(mutability, str):
            raise ArtifactError("stateMutability must be a string")
        if not isinstance(anonymous, bool):
            raise ArtifactError("anonymous must be a boolean")
        indexed[key] = {
            "stateMutability": mutability,
            "outputs": [_abi_type(value) for value in outputs],
            "anonymous": anonymous,
            "indexed": [_event_indexed(value) for value in inputs] if kind == "event" else [],
        }
    return indexed


def _clean_trace(value: dict[str, Any], ignored: frozenset[str]) -> dict[str, Any]:
    return {key: item for key, item in sorted(value.items()) if key not in ignored}


def _is_vacuous(trace: dict[str, Any], ignored: frozenset[str]) -> bool:
    return not any(key != "case" and key not in ignored for key in trace)


def _trace_index(traces: tuple[dict[str, Any], ...], ignored: frozenset[str]) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    for trace in traces:
        case = trace.get("case")
        if not isinstance(case, str) or not case:
            raise ArtifactError("every trace requires a non-empty case string")
        if case in indexed:
            raise ArtifactError(f"duplicate trace case: {case}")
        indexed[case] = _clean_trace(trace, ignored)
    return indexed


def _display(value: Any) -> Any:
    return "<missing>" if value is _MISSING else value


def _mapping_differences(
    category: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    severity: str,
) -> list[Difference]:
    differences: list[Difference] = []
    for key in sorted(set(baseline) | set(candidate)):
        left = baseline.get(key, _MISSING)
        right = candidate.get(key, _MISSING)
        if left != right:
            differences.append(Difference(category, key, severity, _display(left), _display(right)))
    return differences


def _compiler_view(compiler: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in compiler.items() if key != "executable"}


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
    if baseline.bytecode_creation != candidate.bytecode_creation:
        differences.append(
            Difference(
                "bytecode",
                "creation",
                "informational",
                baseline.bytecode_creation,
                candidate.bytecode_creation,
            )
        )
    if baseline.integrity != candidate.integrity:
        differences.append(
            Difference(
                "integrity",
                "metadata",
                "informational",
                baseline.integrity,
                candidate.integrity,
            )
        )
    baseline_compiler = _compiler_view(baseline.compiler)
    candidate_compiler = _compiler_view(candidate.compiler)
    if baseline_compiler != candidate_compiler:
        differences.append(
            Difference(
                "compiler",
                "metadata",
                "informational",
                baseline_compiler,
                candidate_compiler,
            )
        )
    if baseline.source != candidate.source:
        differences.append(
            Difference("source", "metadata", "informational", baseline.source, candidate.source)
        )

    baseline_traces = _trace_index(baseline.traces, policy.ignore_trace_fields)
    candidate_traces = _trace_index(candidate.traces, policy.ignore_trace_fields)
    trace_cases = tuple(sorted(set(baseline_traces) | set(candidate_traces)))
    vacuous = any(
        _is_vacuous(trace, policy.ignore_trace_fields)
        for trace in (*baseline.traces, *candidate.traces)
    )
    if not baseline_traces and not candidate_traces:
        behavior_status = "UNASSESSED"
    else:
        trace_differences = _mapping_differences(
            "traces", baseline_traces, candidate_traces, "semantic"
        )
        differences.extend(trace_differences)
        if trace_differences:
            behavior_status = "FAIL"
        elif vacuous:
            behavior_status = "UNASSESSED"
        else:
            behavior_status = "PASS"

    failing = [difference for difference in differences if difference.category in policy.fail_on]
    if failing:
        status = "FAIL"
    elif behavior_status == "UNASSESSED" and policy.require_traces:
        status = "UNASSESSED"
    else:
        status = "PASS"

    notes: list[str] = []
    if not baseline_traces and not candidate_traces:
        notes.append("no execution traces were present on either side")
    elif vacuous and behavior_status == "UNASSESSED":
        notes.append("one or more traces contain no comparable fields")
    bytecode_paths = {
        difference.path for difference in differences if difference.category == "bytecode"
    }
    if bytecode_paths == {"runtime"}:
        notes.append("runtime bytecode changed; informational unless policy fails on bytecode")
    elif bytecode_paths:
        notes.append("bytecode changed; informational unless policy fails on bytecode")
    if any(difference.category == "compiler" for difference in differences):
        notes.append("compiler metadata changed; informational unless policy fails on compiler")
    return DiffReport(
        status=status,
        baseline=baseline.path,
        candidate=candidate.path,
        behavior_status=behavior_status,
        differences=tuple(differences),
        compared_trace_cases=trace_cases,
        notes=tuple(notes),
    )
