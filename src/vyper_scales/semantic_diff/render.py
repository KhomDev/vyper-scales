from __future__ import annotations

import json
from dataclasses import asdict

from .models import DiffReport


def render_json(report: DiffReport) -> str:
    return json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"


def _short(value: object, limit: int = 96) -> str:
    rendered = json.dumps(value, sort_keys=True, default=str)
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def render_text(report: DiffReport) -> str:
    lines = [
        f"vyper-semantic-diff: {report.status}",
        f"  behavior: {report.behavior_status} ({len(report.compared_trace_cases)} cases)",
    ]
    for difference in report.differences:
        lines.append(f"  {difference.severity.upper():<13} {difference.category}:{difference.path}")
        lines.append(f"      baseline:  {_short(difference.baseline)}")
        lines.append(f"      candidate: {_short(difference.candidate)}")
    for note in report.notes:
        lines.append(f"  note: {note}")
    return "\n".join(lines) + "\n"


def render_markdown(report: DiffReport) -> str:
    lines = [
        "# Vyper semantic diff",
        "",
        f"Overall status: **{report.status}**  ",
        f"Behavior status: **{report.behavior_status}** "
        f"({len(report.compared_trace_cases)} trace cases)",
        "",
        "| Severity | Category | Path | Baseline | Candidate |",
        "|---|---|---|---|---|",
    ]
    for difference in report.differences:
        lines.append(
            f"| {difference.severity} | {difference.category} | `{difference.path}` | "
            f"`{_short(difference.baseline, 48)}` | `{_short(difference.candidate, 48)}` |"
        )
    if not report.differences:
        lines.append("| — | — | — | no differences | no differences |")
    if report.notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in report.notes)
    lines.extend(
        [
            "",
            "> Equality is limited to captured artifacts and replay cases; it is not a",
            "> proof of compiler equivalence for all inputs.",
        ]
    )
    return "\n".join(lines) + "\n"
