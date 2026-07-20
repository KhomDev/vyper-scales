from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from .models import CallSite, Manifest

EXTERNAL_CALL = re.compile(
    r"\b(?P<kind>extcall|staticcall)\s+"
    r"(?P<target>[A-Za-z_][A-Za-z0-9_\.]*"
    r"(?:\(\s*[A-Za-z_][A-Za-z0-9_\.]*\s*\))?)\s*\.\s*"
    r"(?P<method>[A-Za-z_][A-Za-z0-9_]*)\s*\("
)
RAW_CALL = re.compile(r"\braw_call\s*\(\s*(?P<target>[A-Za-z_][A-Za-z0-9_\.]*|0x[0-9a-fA-F]+)")


def _source_files(manifest: Manifest) -> Iterable[Path]:
    seen: set[Path] = set()
    for source in manifest.sources:
        candidate = manifest.root / source
        if candidate.is_dir():
            paths = candidate.rglob("*.vy")
        elif candidate.is_file() and candidate.suffix == ".vy":
            paths = (candidate,)
        else:
            paths = manifest.root.glob(source)
        for path in paths:
            resolved = path.resolve()
            if resolved.is_file() and resolved.suffix == ".vy" and resolved not in seen:
                seen.add(resolved)
                yield resolved


def scan(manifest: Manifest) -> tuple[CallSite, ...]:
    sites: list[CallSite] = []
    for path in sorted(_source_files(manifest)):
        relative = path.relative_to(manifest.root).as_posix()
        text = path.read_text()
        lines = text.splitlines()
        code = "\n".join(line.partition("#")[0] for line in lines)
        for match in EXTERNAL_CALL.finditer(code):
            line_number = code.count("\n", 0, match.start()) + 1
            target = re.sub(r"\s+", "", match.group("target"))
            sites.append(
                CallSite(
                    path=relative,
                    line=line_number,
                    kind=match.group("kind"),
                    target=target,
                    method=match.group("method"),
                    source=lines[line_number - 1].strip(),
                )
            )
        for match in RAW_CALL.finditer(code):
            line_number = code.count("\n", 0, match.start()) + 1
            sites.append(
                CallSite(
                    path=relative,
                    line=line_number,
                    kind="raw_call",
                    target=match.group("target"),
                    method="raw_call",
                    source=lines[line_number - 1].strip(),
                )
            )
    return tuple(sites)
