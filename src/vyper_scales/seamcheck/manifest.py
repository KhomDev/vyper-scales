from __future__ import annotations

import tomllib
from pathlib import Path

from .models import Evidence, Manifest, Seam


class ManifestError(ValueError):
    pass


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ManifestError(f"{field} must be a list of strings")
    return tuple(value)


def _safe_relative(root: Path, value: str, field: str) -> str:
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root):
        raise ManifestError(f"{field} escapes the manifest root: {value}")
    return candidate.relative_to(root).as_posix()


def load_manifest(path: str | Path) -> Manifest:
    manifest_path = Path(path).resolve()
    with manifest_path.open("rb") as handle:
        raw = tomllib.load(handle)

    if raw.get("version") != 1:
        raise ManifestError("manifest version must be 1")

    root = manifest_path.parent
    project = raw.get("project", {})
    if not isinstance(project, dict):
        raise ManifestError("[project] must be a table")

    sources_raw = _strings(project.get("sources", ["src"]), "project.sources")
    sources = tuple(_safe_relative(root, value, "project.sources") for value in sources_raw)
    strict = project.get("strict_unregistered", True)
    if not isinstance(strict, bool):
        raise ManifestError("project.strict_unregistered must be a boolean")
    ignore_calls = _strings(project.get("ignore_calls", []), "project.ignore_calls")

    seams_raw = raw.get("seams", [])
    if not isinstance(seams_raw, list) or not seams_raw:
        raise ManifestError("at least one [[seams]] entry is required")

    seams: list[Seam] = []
    seen: set[str] = set()
    for index, item in enumerate(seams_raw):
        field = f"seams[{index}]"
        if not isinstance(item, dict):
            raise ManifestError(f"{field} must be a table")
        seam_id = item.get("id")
        caller = item.get("caller")
        target = item.get("target")
        if not all(isinstance(value, str) and value for value in (seam_id, caller, target)):
            raise ManifestError(f"{field} requires non-empty id, caller, and target")
        if seam_id in seen:
            raise ManifestError(f"duplicate seam id: {seam_id}")
        seen.add(seam_id)
        caller = _safe_relative(root, caller, f"{field}.caller")
        required = _strings(item.get("required", []), f"{field}.required")

        evidence_raw = item.get("evidence", [])
        if not isinstance(evidence_raw, list):
            raise ManifestError(f"{field}.evidence must be an array")
        evidence: list[Evidence] = []
        for evidence_index, entry in enumerate(evidence_raw):
            evidence_field = f"{field}.evidence[{evidence_index}]"
            if not isinstance(entry, dict) or not isinstance(entry.get("test"), str):
                raise ManifestError(f"{evidence_field} requires a test string")
            test_path, separator, selector = entry["test"].partition("::")
            test_path = _safe_relative(root, test_path, f"{evidence_field}.test")
            test = test_path + (separator + selector if separator else "")
            neighbor = entry.get("neighbor", "")
            if neighbor:
                if not isinstance(neighbor, str):
                    raise ManifestError(f"{evidence_field}.neighbor must be a path")
                neighbor = _safe_relative(root, neighbor, f"{evidence_field}.neighbor")
            note = entry.get("note", "")
            if not isinstance(note, str):
                raise ManifestError(f"{evidence_field}.note must be a string")
            evidence.append(
                Evidence(
                    test=test,
                    covers=_strings(entry.get("covers", []), f"{evidence_field}.covers"),
                    neighbor=neighbor,
                    note=note,
                )
            )

        call_kind = item.get("call_kind", "")
        if call_kind not in {"", "extcall", "staticcall", "raw_call"}:
            raise ManifestError(f"{field}.call_kind is unsupported: {call_kind}")
        risk = item.get("risk", "medium")
        if risk not in {"low", "medium", "high", "critical"}:
            raise ManifestError(f"{field}.risk is unsupported: {risk}")
        rationale = item.get("rationale", "")
        if not isinstance(rationale, str):
            raise ManifestError(f"{field}.rationale must be a string")
        seams.append(
            Seam(
                seam_id=seam_id,
                caller=caller,
                target=target,
                required=required,
                evidence=tuple(evidence),
                call_kind=call_kind,
                risk=risk,
                rationale=rationale,
            )
        )

    return Manifest(
        path=manifest_path,
        root=root,
        sources=sources,
        seams=tuple(seams),
        strict_unregistered=strict,
        ignore_calls=ignore_calls,
    )
