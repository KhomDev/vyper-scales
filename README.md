# Vyper Scales

**Open evidence tooling for Vyper security.**

Three small security tools for failure modes that are easy to describe and still
annoyingly easy to miss in production DeFi systems.

1. **`seamcheck`** turns cross-contract assumptions into a reviewable coverage
   manifest. It finds Vyper external-call sites, verifies that declared seams still
   exist, and fails when required adversarial evidence is missing.
2. **`vyper-semantic-diff`** compares compiler artifacts and replay traces across a
   Vyper upgrade. It separates expected bytecode drift from ABI, selector, storage,
   and behavioral changes.
3. **`vyper-sig-matrix`** generates and checks a signature compatibility matrix for
   EOAs, ERC-1271 wallets, code-bearing EOAs, ERC-6492 counterfactual wallets, and
   ERC-7739 defensive rehashing policies.

The tools are deliberately dependency-light. Their core logic uses only the Python
standard library, their formats are JSON/TOML, and every verdict has a machine-readable
representation. They do not sign, broadcast, or need an RPC endpoint.

## Setup

```bash
uv sync --dev
uv run pytest
uv run ruff check .
```

Run the examples:

```bash
uv run seamcheck --manifest examples/seamcheck/seams.toml

uv run vyper-semantic-diff compare \
  examples/semantic-diff/baseline.json \
  examples/semantic-diff/candidate.json

uv run vyper-sig-matrix generate \
  --policy examples/sig-matrix/policy.toml \
  --format markdown
```

## What these tools do not prove

- A `seamcheck` PASS proves that declared evidence exists and covers declared threat
  dimensions. It does not prove the test itself is correct.
- A semantic-diff PASS proves equality over the captured artifacts and traces. It is
  not a proof of compiler equivalence over all possible inputs.
- A signature-matrix PASS proves the adapter results match the selected policy. It is
  not a cryptographic audit of a wallet implementation.

Those limits are part of the output contract, not fine print.

## Articles

- [`The seam is the security boundary`](articles/01-the-seam-is-the-security-boundary.md)
- [`A compiler upgrade is a protocol migration`](articles/02-a-compiler-upgrade-is-a-protocol-migration.md)
- [`Signatures are a compatibility matrix now`](articles/03-signatures-are-a-compatibility-matrix-now.md)

## License and security

MIT licensed. See [`SECURITY.md`](SECURITY.md) for disclosure and threat-model scope.
These are review tools, not an audit substitute.

Machine-readable schemas and CLI status behavior are documented in
[`docs/formats-and-exit-codes.md`](docs/formats-and-exit-codes.md).
