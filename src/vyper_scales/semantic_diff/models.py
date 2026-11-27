from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Artifact:
    path: str
    compiler: dict[str, Any]
    source: dict[str, Any]
    abi: tuple[dict[str, Any], ...]
    method_identifiers: dict[str, str]
    storage_layout: dict[str, Any]
    bytecode_runtime: str
    bytecode_creation: str
    integrity: str
    traces: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Policy:
    fail_on: frozenset[str] = field(
        default_factory=lambda: frozenset({"abi", "selectors", "storage", "traces"})
    )
    ignore_trace_fields: frozenset[str] = field(
        default_factory=lambda: frozenset({"gas", "gas_used", "execution_time_ns"})
    )
    require_traces: bool = True


@dataclass(frozen=True)
class Difference:
    category: str
    path: str
    severity: str
    baseline: Any
    candidate: Any


@dataclass(frozen=True)
class DiffReport:
    status: str
    baseline: str
    candidate: str
    behavior_status: str
    differences: tuple[Difference, ...]
    compared_trace_cases: tuple[str, ...]
    notes: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        if self.status == "FAIL":
            return 1
        if self.status == "UNASSESSED":
            return 3
        return 0
