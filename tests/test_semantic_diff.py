from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from vyper_scales.semantic_diff.artifact import ArtifactError, load_artifact
from vyper_scales.semantic_diff.cli import main
from vyper_scales.semantic_diff.compare import compare
from vyper_scales.semantic_diff.compiler import CompilerError, compile_artifact
from vyper_scales.semantic_diff.models import Policy
from vyper_scales.semantic_diff.policy import PolicyError, load_policy

FIXTURES = Path(__file__).parents[1] / "examples" / "semantic-diff"


def test_expected_bytecode_and_gas_drift_passes():
    report = compare(
        load_artifact(FIXTURES / "baseline.json"),
        load_artifact(FIXTURES / "candidate.json"),
    )
    assert report.status == "PASS"
    assert report.behavior_status == "PASS"
    assert {difference.category for difference in report.differences} == {"bytecode", "compiler"}


def test_abi_change_fails(tmp_path: Path):
    candidate = json.loads((FIXTURES / "candidate.json").read_text())
    candidate["contract"]["abi"][0]["stateMutability"] = "payable"
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate))
    report = compare(load_artifact(FIXTURES / "baseline.json"), load_artifact(path))
    assert report.status == "FAIL"
    assert any(difference.category == "abi" for difference in report.differences)


def test_trace_state_change_fails(tmp_path: Path):
    candidate = json.loads((FIXTURES / "candidate.json").read_text())
    candidate["traces"][0]["state"]["value"] = "8"
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate))
    report = compare(load_artifact(FIXTURES / "baseline.json"), load_artifact(path))
    assert report.status == "FAIL"
    assert report.behavior_status == "FAIL"


def test_missing_traces_is_unassessed_by_default(tmp_path: Path):
    baseline = json.loads((FIXTURES / "baseline.json").read_text())
    candidate = json.loads((FIXTURES / "candidate.json").read_text())
    baseline["traces"] = []
    candidate["traces"] = []
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps(baseline))
    right.write_text(json.dumps(candidate))
    report = compare(load_artifact(left), load_artifact(right))
    assert report.status == "UNASSESSED"
    assert report.exit_code == 3


def test_policy_can_run_artifact_only_gate(tmp_path: Path):
    baseline = json.loads((FIXTURES / "baseline.json").read_text())
    candidate = json.loads((FIXTURES / "candidate.json").read_text())
    baseline["traces"] = []
    candidate["traces"] = []
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps(baseline))
    right.write_text(json.dumps(candidate))
    policy = Policy(require_traces=False)
    assert compare(load_artifact(left), load_artifact(right), policy).status == "PASS"


def _write_pair(tmp_path: Path, left: dict, right: dict) -> tuple[Path, Path]:
    baseline = tmp_path / "left.json"
    candidate = tmp_path / "right.json"
    baseline.write_text(json.dumps(left))
    candidate.write_text(json.dumps(right))
    return baseline, candidate


def _base_artifact() -> dict:
    return {
        "schema_version": 1,
        "compiler": {
            "executable": "/tmp/vyper",
            "version": "0.4.3",
            "evm_version": "prague",
            "optimize": "gas",
        },
        "source": {"path": "C.vy", "sha256": "abc"},
        "contract": {
            "abi": [],
            "method_identifiers": {"f()": "0x12345678"},
            "layout": {"storage_layout": {}},
            "bytecode_runtime": "0x00",
            "bytecode": "0x11",
            "integrity": "same",
        },
        "traces": [{"case": "c", "success": True, "state": {"value": "1"}, "gas_used": 10}],
    }


def test_omitted_abi_storage_or_bytecode_is_an_error(tmp_path: Path):
    raw = _base_artifact()
    del raw["contract"]["abi"]
    path = tmp_path / "missing.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ArtifactError, match="abi"):
        load_artifact(path)


def test_duplicate_abi_entry_is_an_error(tmp_path: Path):
    raw = _base_artifact()
    raw["contract"]["abi"] = [
        {
            "type": "function",
            "name": "f",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
        },
        {
            "type": "function",
            "name": "f",
            "inputs": [],
            "outputs": [{"name": "", "type": "address"}],
            "stateMutability": "view",
        },
    ]
    left, right = _write_pair(tmp_path, raw, raw)
    with pytest.raises(ArtifactError, match="duplicate ABI entry"):
        compare(load_artifact(left), load_artifact(right))


def test_event_indexed_flag_is_breaking(tmp_path: Path):
    def event(indexed: bool) -> dict:
        raw = _base_artifact()
        raw["contract"]["abi"] = [
            {
                "type": "event",
                "name": "Transfer",
                "anonymous": False,
                "inputs": [
                    {"name": "src", "type": "address", "indexed": indexed},
                    {"name": "value", "type": "uint256", "indexed": False},
                ],
            }
        ]
        return raw

    left, right = _write_pair(tmp_path, event(True), event(False))
    report = compare(load_artifact(left), load_artifact(right))
    assert report.status == "FAIL"
    assert any(difference.category == "abi" for difference in report.differences)


def test_nested_semantic_field_named_gas_is_compared(tmp_path: Path):
    left_raw = _base_artifact()
    right_raw = _base_artifact()
    right_raw["traces"][0]["gas_used"] = 99
    right_raw["traces"][0]["state"] = {"gas": "2", "value": "1"}
    left_raw["traces"][0]["state"] = {"gas": "1", "value": "1"}
    left, right = _write_pair(tmp_path, left_raw, right_raw)
    report = compare(load_artifact(left), load_artifact(right))
    assert report.status == "FAIL"
    assert report.behavior_status == "FAIL"


def test_vacuous_traces_are_unassessed(tmp_path: Path):
    left_raw = _base_artifact()
    right_raw = _base_artifact()
    left_raw["traces"] = [{"case": "c", "gas_used": 1}]
    right_raw["traces"] = [{"case": "c", "gas_used": 9}]
    left, right = _write_pair(tmp_path, left_raw, right_raw)
    report = compare(load_artifact(left), load_artifact(right))
    assert report.status == "UNASSESSED"
    assert report.behavior_status == "UNASSESSED"
    assert report.exit_code == 3


def test_missing_sentinel_does_not_hide_a_selector(tmp_path: Path):
    left_raw = _base_artifact()
    right_raw = _base_artifact()
    left_raw["contract"]["method_identifiers"] = {"f()": "<missing>"}
    right_raw["contract"]["method_identifiers"] = {}
    left, right = _write_pair(tmp_path, left_raw, right_raw)
    report = compare(load_artifact(left), load_artifact(right))
    assert report.status == "FAIL"
    assert any(difference.category == "selectors" for difference in report.differences)


def test_malformed_abi_is_an_error(tmp_path: Path):
    raw = _base_artifact()
    raw["contract"]["abi"] = ["nope"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ArtifactError, match="abi must be an array"):
        load_artifact(path)


def test_compiler_metadata_is_informational_and_path_is_ignored(tmp_path: Path):
    left_raw = _base_artifact()
    right_raw = _base_artifact()
    right_raw["compiler"] = {
        "executable": "/other/vyper",
        "version": "0.4.3",
        "evm_version": "cancun",
        "optimize": "gas",
    }
    left, right = _write_pair(tmp_path, left_raw, right_raw)
    report = compare(load_artifact(left), load_artifact(right))
    assert report.status == "PASS"
    assert any(difference.category == "compiler" for difference in report.differences)
    same = _base_artifact()
    same["compiler"]["executable"] = "/elsewhere/vyper"
    left, right = _write_pair(tmp_path, _base_artifact(), same)
    assert compare(load_artifact(left), load_artifact(right)).differences == ()


def test_creation_bytecode_and_integrity_are_informational(tmp_path: Path):
    left_raw = _base_artifact()
    right_raw = _base_artifact()
    right_raw["contract"]["bytecode"] = "0x22"
    right_raw["contract"]["integrity"] = "other"
    left, right = _write_pair(tmp_path, left_raw, right_raw)
    report = compare(load_artifact(left), load_artifact(right))
    assert report.status == "PASS"
    assert {difference.path for difference in report.differences} == {"creation", "metadata"}
    policy = Policy(fail_on=frozenset({"bytecode", "integrity"}))
    assert compare(load_artifact(left), load_artifact(right), policy).status == "FAIL"


def test_tuple_without_components_is_an_error(tmp_path: Path):
    raw = _base_artifact()
    raw["contract"]["abi"] = [
        {
            "type": "function",
            "name": "f",
            "inputs": [{"name": "value", "type": "tuple"}],
            "outputs": [],
            "stateMutability": "nonpayable",
        }
    ]
    left, right = _write_pair(tmp_path, raw, raw)
    with pytest.raises(ArtifactError, match="components"):
        compare(load_artifact(left), load_artifact(right))


def test_policy_typos_are_rejected(tmp_path: Path):
    path = tmp_path / "policy.toml"
    path.write_text("[pollicy]\nrequire_traces = false\n")
    with pytest.raises(PolicyError, match="unknown policy tables"):
        load_policy(path)
    path.write_text("[policy]\nrequire_trace = false\n")
    with pytest.raises(PolicyError, match="unknown policy fields"):
        load_policy(path)
    shipped = load_policy(FIXTURES / "policy.toml")
    assert shipped.require_traces is True


def test_conflicting_compiler_settings_are_an_error(tmp_path: Path):
    raw = _base_artifact()
    raw["contract"]["settings_dict"] = {"optimize": "codesize"}
    path = tmp_path / "conflict.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ArtifactError, match="settings_dict"):
        load_artifact(path)


def test_settings_dict_is_part_of_compiler_metadata(tmp_path: Path):
    raw = {
        "version": "0.4.3",
        "C.vy": {
            "abi": [],
            "method_identifiers": {},
            "layout": {},
            "bytecode_runtime": "0x",
            "settings_dict": {"evm_version": "prague", "experimental_codegen": False},
        },
    }
    path = tmp_path / "combined.json"
    path.write_text(json.dumps(raw))
    artifact = load_artifact(path)
    assert artifact.compiler["version"] == "0.4.3"
    assert artifact.compiler["evm_version"] == "prague"
    assert artifact.compiler["experimental_codegen"] is False


def test_compiler_invocation_is_contained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    compiler = tmp_path / "vyper"
    compiler.write_text("")
    source = tmp_path / "C.vy"
    source.write_text("# pragma version ~=0.4.3\n")
    outside = tmp_path / "Outside.vy"
    outside.write_text("# pragma version ~=0.4.3\n")
    root = tmp_path / "proj"
    root.mkdir()
    with pytest.raises(CompilerError, match="project_root"):
        compile_artifact(compiler, outside, project_root=root)

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        assert isinstance(command, list)
        assert kwargs.get("shell", False) is False
        calls.append(command)
        if command[1:] == ["--version"]:
            return subprocess.CompletedProcess(command, 0, "0.4.3\n", "")
        if kwargs.get("timeout") == 120 and calls.count(command) == 1:
            body = {
                "version": "0.4.3",
                str(source): {
                    "abi": [],
                    "method_identifiers": {},
                    "layout": {},
                    "bytecode": "0x11",
                    "bytecode_runtime": "0x00",
                    "settings_dict": {"experimental_codegen": True, "optimize": "gas"},
                },
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
        raise AssertionError(command)

    monkeypatch.setattr("vyper_scales.semantic_diff.compiler.subprocess.run", fake_run)
    artifact = compile_artifact(compiler, source)
    assert artifact["compiler"]["experimental_codegen"] is True
    assert all(isinstance(command, list) for command in calls)

    def explode(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs["timeout"])

    monkeypatch.setattr("vyper_scales.semantic_diff.compiler.subprocess.run", explode)
    with pytest.raises(CompilerError, match="timed out"):
        compile_artifact(compiler, source)


def test_example_source_hash_matches_counter_and_cli_passes():
    root = Path(__file__).parents[1]
    digest = hashlib.sha256(
        (root / "examples" / "semantic-diff" / "Counter.vy").read_bytes()
    ).hexdigest()
    for name in ("baseline.json", "candidate.json"):
        artifact = json.loads((root / "examples" / "semantic-diff" / name).read_text())
        assert artifact["source"]["sha256"] == digest
        layout = artifact["contract"]["layout"]["storage_layout"]["value"]
        assert layout["slot"] == 0
        assert layout["type"] == "uint256"
    assert (
        main(
            [
                "compare",
                str(root / "examples" / "semantic-diff" / "baseline.json"),
                str(root / "examples" / "semantic-diff" / "candidate.json"),
            ]
        )
        == 0
    )


def test_article_quotes_the_shipped_semantic_diff(capsys: pytest.CaptureFixture[str]):
    root = Path(__file__).parents[1]
    assert (
        main(
            [
                "compare",
                str(root / "examples" / "semantic-diff" / "baseline.json"),
                str(root / "examples" / "semantic-diff" / "candidate.json"),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out.strip()
    article = (root / "articles" / "02-a-compiler-upgrade-is-a-protocol-migration.md").read_text()
    assert output in article


def test_raw_vyper_combined_json_is_accepted(tmp_path: Path):
    raw = {
        "version": "0.4.3",
        "Counter.vy": {
            "abi": [],
            "method_identifiers": {},
            "layout": {},
            "bytecode_runtime": "0x00",
        },
    }
    path = tmp_path / "combined.json"
    path.write_text(json.dumps(raw))
    artifact = load_artifact(path)
    assert artifact.compiler["version"] == "0.4.3"
    assert artifact.bytecode_runtime == "0x00"
