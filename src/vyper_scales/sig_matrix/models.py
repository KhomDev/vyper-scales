from __future__ import annotations

from dataclasses import dataclass, field


class SignaturePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class SignaturePolicy:
    erc1271: bool = True
    erc6492: bool = False
    erc7739_mode: str = "optional"
    code_bearing_eoa_fallback: bool = True
    enforce_low_s: bool = True
    bind_chain_id: bool = True
    bind_verifying_contract: bool = True
    reject_zero_signer: bool = True

    def __post_init__(self) -> None:
        if self.erc7739_mode not in {"disabled", "optional", "required"}:
            raise SignaturePolicyError(
                "policy.erc7739_mode must be disabled, optional, or required"
            )
        for name, value in (
            ("erc1271", self.erc1271),
            ("erc6492", self.erc6492),
            ("code_bearing_eoa_fallback", self.code_bearing_eoa_fallback),
            ("enforce_low_s", self.enforce_low_s),
            ("bind_chain_id", self.bind_chain_id),
            ("bind_verifying_contract", self.bind_verifying_contract),
            ("reject_zero_signer", self.reject_zero_signer),
        ):
            if not isinstance(value, bool):
                raise SignaturePolicyError(f"policy.{name} must be a boolean")
        if self.erc6492 and not self.erc1271:
            raise SignaturePolicyError("ERC-6492 support requires ERC-1271 support")
        if self.erc7739_mode != "disabled" and not self.erc1271:
            raise SignaturePolicyError("ERC-7739 mode requires ERC-1271 support")


@dataclass(frozen=True)
class MatrixCase:
    case_id: str
    account: str
    signature: str
    wrapper: str
    domain: str
    expected: str
    verification_path: str
    rationale: str
    standards: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Mismatch:
    case_id: str
    expected: str
    observed: str
    expected_path: str
    observed_path: str = ""


@dataclass(frozen=True)
class CheckReport:
    status: str
    policy_fingerprint: str
    expected_cases: int
    observed_cases: int
    missing: tuple[str, ...]
    unexpected: tuple[str, ...]
    mismatches: tuple[Mismatch, ...]

    @property
    def exit_code(self) -> int:
        return 0 if self.status == "PASS" else 1
