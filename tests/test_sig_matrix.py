from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from vyper_scales.sig_matrix.checker import ResultsError, check
from vyper_scales.sig_matrix.matrix import generate_cases
from vyper_scales.sig_matrix.models import SignaturePolicy
from vyper_scales.sig_matrix.policy import SignaturePolicyError, load_policy

POLICY_PATH = Path(__file__).parents[1] / "examples" / "sig-matrix" / "policy.toml"


def _passing_results(policy: SignaturePolicy) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "id": case.case_id,
            "observed": case.expected,
            "path": case.verification_path,
        }
        for case in generate_cases(policy)
    )


def test_default_policy_covers_all_account_families():
    policy = load_policy(POLICY_PATH)
    cases = generate_cases(policy)
    accounts = {case.account for case in cases}
    assert {
        "eoa",
        "deployed-contract-wallet",
        "code-bearing-eoa",
        "counterfactual-wallet",
    } <= accounts
    assert len(cases) == 20


def test_complete_matching_results_pass():
    policy = load_policy(POLICY_PATH)
    report = check(policy, _passing_results(policy))
    assert report.status == "PASS"
    assert report.observed_cases == report.expected_cases


def test_missing_case_fails_closed():
    policy = load_policy(POLICY_PATH)
    observed = _passing_results(policy)[:-1]
    report = check(policy, observed)
    assert report.status == "FAIL"
    assert len(report.missing) == 1


def test_wrong_outcome_and_wrong_path_are_mismatches():
    policy = load_policy(POLICY_PATH)
    observed = list(_passing_results(policy))
    observed[0] = {"id": observed[0]["id"], "observed": "reject", "path": "erc1271"}
    report = check(policy, tuple(observed))
    assert report.status == "FAIL"
    assert report.mismatches[0].case_id == observed[0]["id"]


def test_erc6492_is_opt_in():
    disabled = SignaturePolicy(erc6492=False)
    enabled = replace(disabled, erc6492=True)
    disabled_case = {case.case_id: case for case in generate_cases(disabled)}
    enabled_case = {case.case_id: case for case in generate_cases(enabled)}
    assert disabled_case["erc6492-counterfactual-valid"].expected == "reject"
    assert enabled_case["erc6492-counterfactual-valid"].expected == "accept"


def test_required_erc7739_rejects_raw_digest():
    policy = SignaturePolicy(erc7739_mode="required")
    cases = {case.case_id: case for case in generate_cases(policy)}
    assert cases["erc7739-raw-digest"].expected == "reject"
    assert cases["erc7739-nested-valid"].expected == "accept"


def test_erc7739_without_1271_is_invalid(tmp_path: Path):
    policy = tmp_path / "policy.toml"
    policy.write_text('version = 1\n[policy]\nerc1271 = false\nerc7739_mode = "required"\n')
    with pytest.raises(SignaturePolicyError, match="requires ERC-1271"):
        load_policy(policy)


def test_erc6492_without_1271_is_invalid(tmp_path: Path):
    policy = tmp_path / "policy.toml"
    policy.write_text(
        'version = 1\n[policy]\nerc1271 = false\nerc6492 = true\nerc7739_mode = "disabled"\n'
    )
    with pytest.raises(SignaturePolicyError, match="6492 support requires ERC-1271"):
        load_policy(policy)


def test_code_bearing_eoa_path_does_not_claim_disabled_1271():
    policy = SignaturePolicy(erc1271=False, erc7739_mode="disabled")
    cases = {case.case_id: case for case in generate_cases(policy)}
    assert cases["code-bearing-eoa-ecdsa"].verification_path == "ecrecover"


def test_duplicate_observed_result_is_error():
    policy = load_policy(POLICY_PATH)
    observed = _passing_results(policy)
    with pytest.raises(ResultsError, match="duplicate"):
        check(policy, observed + (observed[0],))


def test_result_shape_is_json_serializable():
    policy = load_policy(POLICY_PATH)
    payload = {"results": list(_passing_results(policy))}
    assert json.loads(json.dumps(payload))["results"][0]["observed"] in {"accept", "reject"}
