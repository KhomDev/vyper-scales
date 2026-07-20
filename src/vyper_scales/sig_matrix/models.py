from __future__ import annotations

from dataclasses import dataclass, field


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
