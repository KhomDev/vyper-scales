from __future__ import annotations

import ast
from fnmatch import fnmatch

from .models import CallSite, Manifest, Report, Seam, SeamResult
from .scanner import scan


def _matches(seam: Seam, site: CallSite) -> bool:
    if seam.caller != site.path:
        return False
    if seam.call_kind and seam.call_kind != site.kind:
        return False
    full = f"{site.target}.{site.method}"
    # Exact equality first so literal brackets in targets are not fnmatch classes.
    return full == seam.target or fnmatch(full, seam.target)


def _selector_parts(selector: str) -> list[str] | None:
    parts = [part for part in selector.split("::") if part]
    if not parts:
        return None
    name, bracket, _rest = parts[-1].partition("[")
    if not name.isidentifier():
        return None
    if bracket and not parts[-1].endswith("]"):
        return None
    parts[-1] = name
    return parts


def _defines_path(body: list[ast.stmt], parts: list[str]) -> bool:
    head, *rest = parts
    for node in body:
        if isinstance(node, ast.ClassDef) and node.name == head:
            if not rest and any(
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                for child in node.body
            ):
                return True
            if rest and _defines_path(node.body, rest):
                return True
        elif (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == head
            and not rest
        ):
            return True
    return False


def _evidence_error(root, test: str) -> str | None:
    test_path, separator, selector = test.partition("::")
    file_path = root / test_path
    if not file_path.is_file():
        return f"evidence test does not exist: {test_path}"
    if not separator or file_path.suffix != ".py":
        return None
    parts = _selector_parts(selector)
    if parts is None:
        return f"evidence test selector is invalid: {selector}"
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=test_path)
    except UnicodeDecodeError:
        return f"evidence test is not valid UTF-8: {test_path}"
    except SyntaxError as exc:
        return f"evidence test cannot be parsed: {test_path}:{exc.lineno or 1}"
    if not _defines_path(tree.body, parts):
        return f"evidence test function not found: {selector}"
    return None


def _ignored(manifest: Manifest, site: CallSite) -> bool:
    return any(fnmatch(site.key, pattern) for pattern in manifest.ignore_calls)


def analyze(manifest: Manifest) -> Report:
    sites, unassessed = scan(manifest)
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
            evidence_error = _evidence_error(manifest.root, evidence.test)
            if evidence_error:
                errors.append(evidence_error)
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
    elif unassessed:
        status = "UNASSESSED"
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
        unassessed=unassessed,
        warnings=warnings,
    )
