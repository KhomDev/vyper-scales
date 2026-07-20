from __future__ import annotations

import json
from pathlib import Path

from vyper_scales.semantic_diff.artifact import load_artifact
from vyper_scales.semantic_diff.compare import compare
from vyper_scales.semantic_diff.models import Policy

FIXTURES = Path(__file__).parents[1] / "examples" / "semantic-diff"


def test_expected_bytecode_and_gas_drift_passes():
    report = compare(
        load_artifact(FIXTURES / "baseline.json"),
        load_artifact(FIXTURES / "candidate.json"),
    )
    assert report.status == "PASS"
    assert report.behavior_status == "PASS"
    assert {difference.category for difference in report.differences} == {"bytecode"}


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
