from __future__ import annotations

import json
from dataclasses import asdict

from .models import Report


def render_json(report: Report) -> str:
    return json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"


def render_text(report: Report) -> str:
    lines = [f"seamcheck: {report.status}"]
    for result in report.seams:
        location = ", ".join(f"{site.path}:{site.line}" for site in result.sites) or "not found"
        lines.append(
            f"  {result.status:<5} {result.seam_id} [{result.risk}] "
            f"sites={location} evidence={result.evidence_count}"
        )
        if result.missing:
            lines.append(f"        missing: {', '.join(result.missing)}")
        for error in result.errors:
            lines.append(f"        error: {error}")
    for site in report.unregistered:
        lines.append(
            f"  UNREGISTERED {site.path}:{site.line} {site.kind} {site.target}.{site.method}"
        )
    for call in report.unassessed:
        lines.append(f"  UNASSESSED {call.path}:{call.line} {call.kind} syntax was not classified")
    for warning in report.warnings:
        lines.append(f"  warning: {warning}")
    return "\n".join(lines) + "\n"


def render_markdown(report: Report) -> str:
    lines = [
        "# Seam coverage report",
        "",
        f"Overall status: **{report.status}**",
        "",
        "| Seam | Risk | Status | Evidence | Missing |",
        "|---|---:|---:|---:|---|",
    ]
    for result in report.seams:
        missing = ", ".join(result.missing) or "—"
        lines.append(
            f"| `{result.seam_id}` | {result.risk} | **{result.status}** | "
            f"{result.evidence_count} | {missing} |"
        )
    if report.unregistered:
        lines.extend(["", "## Unregistered external calls", ""])
        lines.extend(
            f"- `{site.path}:{site.line}` — `{site.kind} {site.target}.{site.method}`"
            for site in report.unregistered
        )
    if report.unassessed:
        lines.extend(["", "## Unassessed calls", ""])
        lines.extend(
            f"- `{call.path}:{call.line}` — `{call.kind}` syntax was not classified"
            for call in report.unassessed
        )
    lines.extend(
        [
            "",
            "> A PASS verifies manifest completeness over declared evidence. It does not prove",
            "> that an evidence test is a faithful model of its production neighbor.",
        ]
    )
    return "\n".join(lines) + "\n"
