from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .artifact import ArtifactError, _contract_payload, _merge_settings


class CompilerError(RuntimeError):
    pass


def _run(
    command: list[str], *, cwd: Path | None = None, timeout: int
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CompilerError(f"compiler timed out after {timeout} seconds") from exc


def _executable(value: str) -> str:
    resolved = shutil.which(value)
    if resolved is None:
        candidate = Path(value).resolve()
        if not candidate.is_file():
            raise CompilerError(f"compiler executable not found: {value}")
        resolved = str(candidate)
    return resolved


def compile_artifact(
    compiler: str,
    source: str | Path,
    *,
    evm_version: str = "prague",
    optimize: str = "gas",
    project_root: str | Path | None = None,
    traces: str | Path | None = None,
) -> dict[str, Any]:
    executable = _executable(compiler)
    source_path = Path(source).resolve()
    root = Path(project_root).resolve() if project_root else source_path.parent
    if not source_path.is_relative_to(root):
        raise CompilerError("source must be inside project_root")

    command = [
        executable,
        "-f",
        "combined_json",
        "--evm-version",
        evm_version,
        "-O",
        optimize,
        "-p",
        str(root),
        str(source_path),
    ]
    completed = _run(command, cwd=root, timeout=120)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise CompilerError(f"compiler exited {completed.returncode}: {message}")
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CompilerError("compiler did not return combined_json") from exc
    if not isinstance(raw, dict):
        raise CompilerError("combined_json root must be an object")
    try:
        contract = _contract_payload(raw)
    except ArtifactError as exc:
        raise CompilerError(str(exc)) from exc

    version_result = _run([executable, "--version"], timeout=10)
    if version_result.returncode != 0:
        message = version_result.stderr.strip() or version_result.stdout.strip()
        raise CompilerError(f"compiler --version exited {version_result.returncode}: {message}")
    version = version_result.stdout.strip()
    if not version:
        raise CompilerError("compiler --version returned no output")
    trace_values: list[dict[str, Any]] = []
    if traces:
        try:
            loaded = json.loads(Path(traces).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CompilerError(f"invalid trace JSON: {exc}") from exc
        trace_values = loaded.get("traces", loaded) if isinstance(loaded, dict) else loaded
        if not isinstance(trace_values, list) or not all(
            isinstance(item, dict) for item in trace_values
        ):
            raise CompilerError("trace input must be an array or an object with traces")

    compiler_meta: dict[str, Any] = {
        "executable": executable,
        "version": version,
        "evm_version": evm_version,
        "optimize": optimize,
    }
    try:
        _merge_settings(compiler_meta, contract.get("settings_dict"))
    except ArtifactError as exc:
        raise CompilerError(str(exc)) from exc

    return {
        "schema_version": 1,
        "compiler": compiler_meta,
        "source": {
            "path": source_path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        },
        "contract": contract,
        "traces": trace_values,
    }
