from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CallSite:
    path: str
    line: int
    kind: str
    target: str
    method: str
    source: str

    @property
    def key(self) -> str:
        return f"{self.path}:{self.target}.{self.method}"


@dataclass(frozen=True)
class Evidence:
    test: str
    covers: tuple[str, ...]
    neighbor: str = ""
    note: str = ""


@dataclass(frozen=True)
class Seam:
    seam_id: str
    caller: str
    target: str
    required: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    call_kind: str = ""
    risk: str = "medium"
    rationale: str = ""


@dataclass(frozen=True)
class Manifest:
    path: Path
    root: Path
    sources: tuple[str, ...]
    seams: tuple[Seam, ...]
    strict_unregistered: bool = True
    ignore_calls: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeamResult:
    seam_id: str
    status: str
    risk: str
    sites: tuple[CallSite, ...]
    covered: tuple[str, ...]
    missing: tuple[str, ...]
    errors: tuple[str, ...]
    evidence_count: int


@dataclass(frozen=True)
class Report:
    manifest: str
    status: str
    seams: tuple[SeamResult, ...]
    unregistered: tuple[CallSite, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def exit_code(self) -> int:
        if any(result.status == "ERROR" for result in self.seams):
            return 2
        if self.status == "GAP":
            return 1
        return 0
