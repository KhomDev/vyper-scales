from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from .manifest import ManifestError
from .models import CallSite, Manifest, UnassessedCall

KEYWORD = re.compile(r"\b(?P<kind>extcall|staticcall|raw_call)\b")


def _mask_non_code(text: str, relative: str) -> str:
    """Replace comments and string literals with spaces without moving indexes."""
    chars = list(text)
    index = 0
    size = len(chars)
    while index < size:
        if chars[index] == "#":
            while index < size and chars[index] != "\n":
                chars[index] = " "
                index += 1
            continue
        if chars[index] != '"':
            index += 1
            continue
        triple = index + 2 < size and chars[index + 1] == '"' and chars[index + 2] == '"'
        if triple:
            end = text.find('"""', index + 3)
            if end == -1:
                raise ManifestError(f"unterminated string in {relative}")
            for cursor in range(index, end + 3):
                if chars[cursor] != "\n":
                    chars[cursor] = " "
            index = end + 3
            continue
        chars[index] = " "
        cursor = index + 1
        closed = False
        while cursor < size and chars[cursor] != "\n":
            if chars[cursor] == "\\":
                chars[cursor] = " "
                cursor += 1
                if cursor < size and chars[cursor] != "\n":
                    chars[cursor] = " "
                    cursor += 1
                continue
            if chars[cursor] == '"':
                chars[cursor] = " "
                closed = True
                cursor += 1
                break
            chars[cursor] = " "
            cursor += 1
        if not closed:
            raise ManifestError(f"unterminated string in {relative}")
        index = cursor
    return "".join(chars)


def _skip_ws(code: str, index: int) -> int:
    while index < len(code) and code[index].isspace():
        index += 1
    return index


def _skip_inline_ws(code: str, index: int) -> int:
    while index < len(code) and code[index] in " \t":
        index += 1
    return index


def _identifier(code: str, index: int) -> tuple[str, int] | None:
    if index >= len(code) or not (code[index].isalpha() or code[index] == "_"):
        return None
    end = index + 1
    while end < len(code) and (code[end].isalnum() or code[end] == "_"):
        end += 1
    return code[index:end], end


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _parse_attribute_call(code: str, index: int) -> tuple[str, str] | None:
    index = _skip_ws(code, index)
    start = index
    depth = 0
    while index < len(code):
        char = code[index]
        if char in "([{":
            depth += 1
            index += 1
            continue
        if char in ")]}":
            if depth == 0:
                return None
            depth -= 1
            index += 1
            continue
        if char == "\n" and depth == 0:
            return None
        if char == "." and depth == 0:
            name_index = _skip_inline_ws(code, index + 1)
            ident = _identifier(code, name_index)
            if ident is not None:
                name, after_name = ident
                paren = _skip_inline_ws(code, after_name)
                if paren < len(code) and code[paren] == "(":
                    target = _normalize(code[start:index])
                    if target:
                        return target, name
                    return None
        index += 1
    return None


def _parse_raw_target(code: str, index: int) -> str | None:
    index = _skip_ws(code, index)
    if index >= len(code) or code[index] != "(":
        return None
    index += 1
    start = _skip_ws(code, index)
    depth = 0
    cursor = start
    while cursor < len(code):
        char = code[cursor]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif char == "," and depth == 0:
            break
        cursor += 1
    else:
        return None
    target = _normalize(code[start:cursor])
    return target or None


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _calls_in_source(relative: str, text: str) -> tuple[list[CallSite], list[UnassessedCall]]:
    masked = _mask_non_code(text, relative)
    lines = text.splitlines()
    sites: list[CallSite] = []
    unassessed: list[UnassessedCall] = []
    for match in KEYWORD.finditer(masked):
        kind = match.group("kind")
        line_number = _line_number(text, match.start())
        source = lines[line_number - 1].strip() if lines else ""
        if kind == "raw_call":
            target = _parse_raw_target(masked, match.end())
            if target is None:
                unassessed.append(UnassessedCall(relative, line_number, kind, source))
                continue
            sites.append(CallSite(relative, line_number, kind, target, "raw_call", source))
            continue
        parsed = _parse_attribute_call(masked, match.end())
        if parsed is None:
            unassessed.append(UnassessedCall(relative, line_number, kind, source))
            continue
        target, method = parsed
        sites.append(CallSite(relative, line_number, kind, target, method, source))
    return sites, unassessed


def _source_files(manifest: Manifest) -> Iterable[Path]:
    root = manifest.root.resolve()
    seen: set[Path] = set()
    for source in manifest.sources:
        candidate = manifest.root / source
        if candidate.is_dir():
            paths: Iterable[Path] = candidate.rglob("*.vy")
        elif candidate.is_file() and candidate.suffix == ".vy":
            paths = (candidate,)
        else:
            paths = manifest.root.glob(source)
        for path in paths:
            if path in seen or path.suffix != ".vy":
                continue
            try:
                displayed = path.relative_to(root).as_posix()
            except ValueError as exc:
                raise ManifestError(f"source escapes the manifest root: {path}") from exc
            resolved = path.resolve()
            if not resolved.is_file():
                continue
            if not resolved.is_relative_to(root):
                raise ManifestError(f"source escapes the manifest root: {displayed}")
            seen.add(path)
            yield path


def scan(manifest: Manifest) -> tuple[tuple[CallSite, ...], tuple[UnassessedCall, ...]]:
    sites: list[CallSite] = []
    unassessed: list[UnassessedCall] = []
    root = manifest.root.resolve()
    for path in sorted(_source_files(manifest), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ManifestError(f"source is not valid UTF-8: {relative}") from exc
        found, unknown = _calls_in_source(relative, text)
        sites.extend(found)
        unassessed.extend(unknown)
    return tuple(sites), tuple(unassessed)
