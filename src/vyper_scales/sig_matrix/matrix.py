from __future__ import annotations

from .models import MatrixCase, SignaturePolicy


def _case(
    case_id: str,
    account: str,
    signature: str,
    expected: str,
    verification_path: str,
    rationale: str,
    *standards: str,
    wrapper: str = "none",
    domain: str = "bound",
) -> MatrixCase:
    return MatrixCase(
        case_id=case_id,
        account=account,
        signature=signature,
        wrapper=wrapper,
        domain=domain,
        expected=expected,
        verification_path=verification_path,
        rationale=rationale,
        standards=tuple(standards),
    )


def generate_cases(policy: SignaturePolicy) -> tuple[MatrixCase, ...]:
    cases = [
        _case(
            "eoa-valid-canonical",
            "eoa",
            "valid-low-s-v27-or-28",
            "accept",
            "ecrecover",
            "Canonical ECDSA signature recovers the declared signer.",
            "EIP-712",
        ),
        _case(
            "eoa-wrong-signer",
            "eoa",
            "recovers-other-address",
            "reject",
            "ecrecover",
            "A valid signature for another address is not authorization.",
            "EIP-712",
        ),
        _case(
            "eoa-malformed",
            "eoa",
            "wrong-length",
            "reject",
            "parse-reject",
            "Malformed signatures must not reach a permissive fallback.",
        ),
        _case(
            "eoa-invalid-v",
            "eoa",
            "v-outside-27-28",
            "reject",
            "canonicality-reject",
            "The verifier accepts one explicit v convention.",
        ),
        _case(
            "eoa-high-s",
            "eoa",
            "valid-high-s-twin",
            "reject" if policy.enforce_low_s else "accept",
            "canonicality-reject" if policy.enforce_low_s else "ecrecover",
            "Low-s enforcement removes the malleable twin signature.",
            "EIP-2",
        ),
        _case(
            "zero-signer",
            "zero-address",
            "zero-recovery",
            "reject" if policy.reject_zero_signer else "accept",
            "zero-signer-guard" if policy.reject_zero_signer else "ecrecover",
            "A failed recovery must not authorize an empty signer.",
        ),
        _case(
            "chain-domain-replay",
            "eoa",
            "valid-on-other-chain",
            "reject" if policy.bind_chain_id else "accept",
            "domain-separator" if policy.bind_chain_id else "ecrecover",
            "The signed domain should bind the intended chain.",
            "EIP-712",
            domain="other-chain",
        ),
        _case(
            "verifier-domain-replay",
            "eoa",
            "valid-for-other-contract",
            "reject" if policy.bind_verifying_contract else "accept",
            "domain-separator" if policy.bind_verifying_contract else "ecrecover",
            "The signed domain should bind the intended verifying contract.",
            "EIP-712",
            domain="other-verifying-contract",
        ),
    ]

    if policy.erc1271:
        cases.extend(
            [
                _case(
                    "erc1271-magic",
                    "deployed-contract-wallet",
                    "wallet-approved",
                    "accept",
                    "erc1271-staticcall",
                    "Only an exact successful magic-value response authorizes the digest.",
                    "ERC-1271",
                ),
                _case(
                    "erc1271-wrong-magic",
                    "deployed-contract-wallet",
                    "wallet-rejected",
                    "reject",
                    "erc1271-staticcall",
                    "Success with a non-magic return value is still rejection.",
                    "ERC-1271",
                ),
                _case(
                    "erc1271-revert",
                    "deployed-contract-wallet",
                    "wallet-reverts",
                    "reject",
                    "erc1271-staticcall",
                    "A wallet revert is an invalid signature, not a settlement-wide exception.",
                    "ERC-1271",
                ),
                _case(
                    "erc1271-short-return",
                    "deployed-contract-wallet",
                    "short-magic-prefix",
                    "reject",
                    "erc1271-staticcall",
                    "A four-byte prefix in malformed return data must not be over-read as success.",
                    "ERC-1271",
                ),
            ]
        )

    if policy.erc1271:
        code_eoa_path = "erc1271->ecrecover" if policy.code_bearing_eoa_fallback else "erc1271-only"
    else:
        code_eoa_path = "ecrecover" if policy.code_bearing_eoa_fallback else "policy-reject"

    cases.extend(
        [
            _case(
                "code-bearing-eoa-ecdsa",
                "code-bearing-eoa",
                "valid-eoa-signature",
                "accept" if policy.code_bearing_eoa_fallback else "reject",
                code_eoa_path,
                "Code presence alone must not erase EOA signature compatibility.",
                "EIP-7702",
                "ERC-1271",
            ),
            _case(
                "code-bearing-eoa-invalid",
                "code-bearing-eoa",
                "1271-fails-and-ecdsa-wrong",
                "reject",
                code_eoa_path,
                "Trying two routes must not turn two failures into acceptance.",
                "EIP-7702",
                "ERC-1271",
            ),
        ]
    )

    counterfactual_expected = "accept" if policy.erc6492 else "reject"
    counterfactual_path = "erc6492-universal-validator" if policy.erc6492 else "policy-reject"
    cases.extend(
        [
            _case(
                "erc6492-counterfactual-valid",
                "counterfactual-wallet",
                "factory-deploys-and-wallet-accepts",
                counterfactual_expected,
                counterfactual_path,
                "Counterfactual signatures need an explicit, trusted validation path.",
                "ERC-6492",
                wrapper="erc6492",
            ),
            _case(
                "erc6492-factory-revert",
                "counterfactual-wallet",
                "factory-reverts",
                "reject",
                counterfactual_path,
                "A failed prepare/deploy step cannot authorize the signer.",
                "ERC-6492",
                wrapper="erc6492",
            ),
            _case(
                "erc6492-inner-invalid",
                "counterfactual-wallet",
                "factory-succeeds-wallet-rejects",
                "reject",
                counterfactual_path,
                "Deployment success is not signature success.",
                "ERC-6492",
                wrapper="erc6492",
            ),
        ]
    )

    if policy.erc7739_mode != "disabled":
        raw_expected = "reject" if policy.erc7739_mode == "required" else "accept"
        cases.extend(
            [
                _case(
                    "erc7739-nested-valid",
                    "deployed-contract-wallet",
                    "wallet-approved",
                    "accept",
                    "erc7739-rehash->erc1271-staticcall",
                    "The wallet validates a nested domain-bound digest.",
                    "ERC-7739",
                    "ERC-1271",
                    domain="nested",
                ),
                _case(
                    "erc7739-raw-digest",
                    "deployed-contract-wallet",
                    "wallet-approved-raw",
                    raw_expected,
                    "erc7739-policy" if policy.erc7739_mode == "required" else "erc1271-staticcall",
                    "Required mode rejects raw digests that omit defensive rehashing.",
                    "ERC-7739",
                    "ERC-1271",
                    domain="raw",
                ),
                _case(
                    "erc7739-wrong-app-domain",
                    "deployed-contract-wallet",
                    "nested-for-other-app",
                    "reject",
                    "erc7739-rehash->erc1271-staticcall",
                    "Nested signatures remain bound to the application domain.",
                    "ERC-7739",
                    domain="nested-other-app",
                ),
            ]
        )
    return tuple(cases)
