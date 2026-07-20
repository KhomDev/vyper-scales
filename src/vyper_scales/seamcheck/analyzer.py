from __future__ import annotations

from fnmatch import fnmatch

from .models import CallSite, Manifest, Report, Seam, SeamResult
from .scanner import scan


def _matches(seam: Seam, site: CallSite) -> bool:
    if seam.caller != site.path:
        return False
    if seam.call_kind and seam.call_kind != site.kind:
        return False
    return fnmatch(f"{site.target}.{site.method}", seam.target) or fnmatch(site.method, seam.target)


def _ignored(manifest: Manifest, site: CallSite) -> bool:
    return any(fnmatch(site.key, pattern) for pattern in manifest.ignore_calls)


def analyze(manifest: Manifest) -> Report:
    sites = scan(manifest)
    results: list[SeamResult] = []
    registered: set[CallSite] = set()

    for seam in manifest.seams:
        matched = tuple(site for site in sites if _matches(seam, site))
        registered.update(matched)
        covered = sorted({cover for evidence in seam.evidence for cover in evidence.covers})
        missing = sorted(set(seam.required) - set(covered))
        errors: list[str] = []
        if not (manifest.root / seam.caller).is_file():
            errors.append(f"caller does not exist: {seam.caller}")
        if not matched:
            errors.append(f"declared call site not found: {seam.target}")
        for evidence in seam.evidence:
            test_path = evidence.test.partition("::")[0]
            if not (manifest.root / test_path).is_file():
                errors.append(f"evidence test does not exist: {test_path}")
            if evidence.neighbor and not (manifest.root / evidence.neighbor).is_file():
                errors.append(f"neighbor source does not exist: {evidence.neighbor}")

        status = "ERROR" if errors else "GAP" if missing else "PASS"
        results.append(
            SeamResult(
                seam_id=seam.seam_id,
                status=status,
                risk=seam.risk,
                sites=matched,
                covered=tuple(covered),
                missing=tuple(missing),
                errors=tuple(errors),
                evidence_count=len(seam.evidence),
            )
        )

    unregistered = tuple(
        site for site in sites if site not in registered and not _ignored(manifest, site)
    )
    if any(result.status == "ERROR" for result in results):
        status = "ERROR"
    elif any(result.status == "GAP" for result in results) or (
        manifest.strict_unregistered and unregistered
    ):
        status = "GAP"
    else:
        status = "PASS"

    warnings = ()
    if unregistered and not manifest.strict_unregistered:
        warnings = (f"{len(unregistered)} unregistered external call(s) ignored by policy",)
    return Report(
        manifest=manifest.path.as_posix(),
        status=status,
        seams=tuple(results),
        unregistered=unregistered,
        warnings=warnings,
    )
