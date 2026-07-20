from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Artifact


class ArtifactError(ValueError):
    pass


def _contract_payload(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("schema_version") == 1 and isinstance(raw.get("contract"), dict):
        return raw["contract"]
    if any(key in raw for key in ("abi", "method_identifiers", "layout", "storage_layout")):
        return raw
    candidates = [
        value
        for key, value in raw.items()
        if key != "version" and isinstance(value, dict) and isinstance(value.get("abi"), list)
    ]
    if len(candidates) != 1:
        raise ArtifactError("artifact must contain exactly one contract payload")
    return candidates[0]


def load_artifact(path: str | Path) -> Artifact:
    artifact_path = Path(path).resolve()
    try:
        raw = json.loads(artifact_path.read_text())
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"invalid JSON in {artifact_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ArtifactError("artifact root must be a JSON object")
    payload = _contract_payload(raw)

    abi = payload.get("abi", [])
    methods = payload.get("method_identifiers", {})
    layout = payload.get("storage_layout", payload.get("layout", {}))
    traces = raw.get("traces", payload.get("traces", []))
    if not isinstance(abi, list):
        raise ArtifactError("abi must be an array")
    if not isinstance(methods, dict):
        raise ArtifactError("method_identifiers must be an object")
    if not isinstance(layout, dict):
        raise ArtifactError("storage layout must be an object")
    if not isinstance(traces, list) or not all(isinstance(item, dict) for item in traces):
        raise ArtifactError("traces must be an array of objects")

    bytecode = payload.get("bytecode_runtime", payload.get("deployed_bytecode", ""))
    if isinstance(bytecode, dict):
        bytecode = bytecode.get("bytecode", "")
    compiler = raw.get("compiler", {})
    if not compiler and isinstance(raw.get("version"), str):
        compiler = {"version": raw["version"]}
    source = raw.get("source", {})
    if not isinstance(compiler, dict) or not isinstance(source, dict):
        raise ArtifactError("compiler and source metadata must be objects")

    return Artifact(
        path=artifact_path.as_posix(),
        compiler=compiler,
        source=source,
        abi=tuple(abi),
        method_identifiers={str(key): str(value) for key, value in methods.items()},
        storage_layout=layout,
        bytecode_runtime=str(bytecode),
        integrity=str(payload.get("integrity", raw.get("integrity", ""))),
        traces=tuple(traces),
    )
