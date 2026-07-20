from __future__ import annotations

import json
from dataclasses import asdict

from .models import CheckReport, MatrixCase, SignaturePolicy
from .policy import fingerprint


def render_cases_json(policy: SignaturePolicy, cases: tuple[MatrixCase, ...]) -> str:
    payload = {
        "schema_version": 1,
        "policy_fingerprint": fingerprint(policy),
        "policy": asdict(policy),
        "cases": [asdict(case) for case in cases],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_cases_markdown(policy: SignaturePolicy, cases: tuple[MatrixCase, ...]) -> str:
    lines = [
        "# Signature compatibility matrix",
        "",
        f"Policy fingerprint: `{fingerprint(policy)}`",
        "",
        "| Case | Account | Signature/domain | Expected | Path |",
        "|---|---|---|---:|---|",
    ]
    for case in cases:
        context = case.signature if case.domain == "bound" else f"{case.signature} / {case.domain}"
        lines.append(
            f"| `{case.case_id}` | {case.account} | {context} | **{case.expected}** | "
            f"`{case.verification_path}` |"
        )
    lines.extend(
        [
            "",
            "> Expected outcomes come from the selected policy. Run every case against the",
            "> actual verifier and feed observed outcomes back to `vyper-sig-matrix check`.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_check_json(report: CheckReport) -> str:
    return json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"


def render_check_text(report: CheckReport) -> str:
    lines = [
        f"vyper-sig-matrix: {report.status}",
        f"  cases: {report.observed_cases}/{report.expected_cases}",
        f"  policy: {report.policy_fingerprint}",
    ]
    if report.missing:
        lines.append(f"  missing: {', '.join(report.missing)}")
    if report.unexpected:
        lines.append(f"  unexpected: {', '.join(report.unexpected)}")
    for mismatch in report.mismatches:
        lines.append(
            f"  MISMATCH {mismatch.case_id}: expected={mismatch.expected} "
            f"observed={mismatch.observed}"
        )
        if mismatch.observed_path:
            lines.append(
                f"      path expected={mismatch.expected_path} observed={mismatch.observed_path}"
            )
    return "\n".join(lines) + "\n"
