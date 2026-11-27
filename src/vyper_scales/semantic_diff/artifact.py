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
        raw = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"invalid JSON in {artifact_path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ArtifactError(f"artifact is not valid UTF-8: {artifact_path}") from exc
    if not isinstance(raw, dict):
        raise ArtifactError("artifact root must be a JSON object")
    payload = _contract_payload(raw)

    missing: list[str] = []
    if "abi" not in payload:
        missing.append("abi")
    if "method_identifiers" not in payload:
        missing.append("method_identifiers")
    if "layout" not in payload and "storage_layout" not in payload:
        missing.append("storage layout")
    if "bytecode_runtime" not in payload and "deployed_bytecode" not in payload:
        missing.append("bytecode_runtime")
    if missing:
        raise ArtifactError("artifact is missing required fields: " + ", ".join(missing))

    abi = payload["abi"]
    methods = payload["method_identifiers"]
    layout = payload["storage_layout"] if "storage_layout" in payload else payload["layout"]
    if "traces" in raw:
        traces = raw["traces"]
    elif "traces" in payload:
        traces = payload["traces"]
    else:
        traces = []
    if not isinstance(abi, list) or not all(isinstance(item, dict) for item in abi):
        raise ArtifactError("abi must be an array of objects")
    if not isinstance(methods, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in methods.items()
    ):
        raise ArtifactError("method_identifiers must be an object of strings")
    if not isinstance(layout, dict):
        raise ArtifactError("storage layout must be an object")
    if not isinstance(traces, list) or not all(isinstance(item, dict) for item in traces):
        raise ArtifactError("traces must be an array of objects")

    bytecode = _bytecode_string(
        payload["bytecode_runtime"]
        if "bytecode_runtime" in payload
        else payload["deployed_bytecode"],
        "bytecode_runtime",
    )
    creation = ""
    if "bytecode" in payload:
        creation = _bytecode_string(payload["bytecode"], "bytecode")
    compiler = raw.get("compiler", {})
    if not compiler and isinstance(raw.get("version"), str):
        compiler = {"version": raw["version"]}
    if not isinstance(compiler, dict):
        raise ArtifactError("compiler metadata must be an object")
    compiler = dict(compiler)
    _merge_settings(compiler, payload.get("settings_dict"))
    source = raw.get("source", {})
    if not isinstance(source, dict):
        raise ArtifactError("source metadata must be an object")
    integrity = payload.get("integrity", raw.get("integrity", ""))
    if not isinstance(integrity, str):
        raise ArtifactError("integrity must be a string")

    return Artifact(
        path=artifact_path.as_posix(),
        compiler=compiler,
        source=source,
        abi=tuple(abi),
        method_identifiers=dict(methods),
        storage_layout=layout,
        bytecode_runtime=bytecode,
        bytecode_creation=creation,
        integrity=integrity,
        traces=tuple(traces),
    )


def _merge_settings(compiler: dict[str, Any], settings: object) -> None:
    if settings is None:
        return
    if not isinstance(settings, dict):
        raise ArtifactError("settings_dict must be an object")
    for key, value in settings.items():
        if key in compiler and compiler[key] != value:
            raise ArtifactError(
                f"compiler {key} does not match settings_dict ({compiler[key]!r} != {value!r})"
            )
        compiler.setdefault(key, value)


def _bytecode_string(value: object, field: str) -> str:
    if isinstance(value, dict):
        inner = value.get("bytecode")
        if not isinstance(inner, str):
            raise ArtifactError(f"{field} object must contain a bytecode string")
        return inner
    if not isinstance(value, str):
        raise ArtifactError(f"{field} must be a string")
    return value
