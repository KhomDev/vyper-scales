# Signatures are a compatibility matrix now

*A Vyper test matrix for EOAs, ERC-1271 wallets, code-bearing EOAs, counterfactual
accounts, and defensive typed-data rehashing.*

---

“If the signer has code, call ERC-1271. Otherwise use `ecrecover`.”

That rule used to be a reasonable summary. It is no longer a sufficient verification
policy.

Contract wallets can validate arbitrary signature schemes through ERC-1271. ERC-6492 can
wrap a signature for a wallet that is not deployed yet. EIP-7702 allows an externally
owned account to carry a delegation indicator in its code. ERC-7739 adds defensive
rehashing for typed signatures across smart accounts. ECDSA still has canonicality,
zero-address, domain, and replay edges underneath all of it.

The result is not one signature path. It is a compatibility matrix.

That matrix is easy to discuss and easy to test incompletely. A suite often has one valid
EOA case and one valid smart-wallet case. Both pass. The verifier still bricks a
code-bearing EOA, accepts a raw digest that policy meant to bind, bubbles a wallet revert
through an entire batch, or treats counterfactual deployment success as signature success.

I built `vyper-sig-matrix` to make the missing cells visible. A TOML policy generates a
set of accept/reject cases and expected verification routes. A protocol adapter runs
those cases against the real verifier. The checker fails on a wrong outcome, a wrong
route, an unexpected case, or a missing result.

The tool does not perform cryptography. That is deliberate. The contract, wallet, or
universal validator remains the system under test. The public artifact is the matrix that
stops “supports smart wallets” from standing in for twenty different claims.

## Start with the base ECDSA path

Smart-account support does not make the ordinary EOA path less important. It makes a
precise EOA policy more important because fallbacks now cross account categories.

A robust `(r, s, v)` path should answer at least these questions:

- Is the signature exactly the expected length and encoding?
- Does `v` use `27/28`, `0/1`, or an explicitly normalized convention?
- Is `s` in the lower half of the secp256k1 order?
- Does recovery equal the declared signer?
- Is the recovered address non-zero?
- Does the signed digest bind `chainId`?
- Does it bind the verifying contract?
- Does it bind nonce, deadline, action, and all value-bearing fields?

The ERC-1271 specification's reference material includes low-`s`, valid-`v`, and
non-zero-recovery checks for its ECDSA example. EIP-7702 also requires authorization
tuple `s` to be at most `secp256k1n/2`, referring to EIP-2.

Those are not cryptographic decoration. They determine whether two encodings can represent
the same authorization, whether a failed recovery can collide with an empty owner, and
whether a signature can move between domains.

The generated matrix includes:

```text
eoa-valid-canonical       accept  ecrecover
eoa-wrong-signer          reject  ecrecover
eoa-malformed             reject  parse-reject
eoa-invalid-v             reject  canonicality-reject
eoa-high-s                reject  canonicality-reject
zero-signer               reject  zero-signer-guard
chain-domain-replay       reject  domain-separator
verifier-domain-replay    reject  domain-separator
```

If a protocol intentionally accepts `v = 0/1`, that can be a valid policy. It needs an
explicit normalization case. Ambiguity is the problem, not the convention itself.

## ERC-1271: exact magic, static context, failure isolation

[ERC-1271](https://eips.ethereum.org/EIPS/eip-1271) defines
`isValidSignature(bytes32,bytes)` for contract-based signers. A valid result is the exact
four-byte magic value `0x1626ba7e`. The call must not modify state, and the specification
allows the wallet to make external calls and apply context-dependent rules.

Three details follow from that design.

First, call success is not signature success. A wallet can return `0xffffffff`, zeros, a
short value, or another well-formed value. Only the expected magic authorizes the digest.

Second, a wallet revert should normally become “invalid signature” for that order, not a
revert that aborts unrelated orders in a batch. A Vyper verifier can use `raw_call` with
`is_static_call=True` and `revert_on_failure=False`, inspect the success flag and return
length, then compare the first four bytes only when the response is structurally valid.

Third, ERC-1271 is not “ECDSA inside a contract.” The wallet can use multisig, session
keys, BLS, time-based policy, modules, or state. The application verifies the wallet's
decision, not its internal signature scheme.

The minimum negative matrix is therefore:

```text
erc1271-magic          accept  exact 32-byte ABI response containing magic
erc1271-wrong-magic    reject  successful call, non-magic value
erc1271-revert         reject  failed static call
erc1271-short-return   reject  malformed response
```

A single “Safe signature works” test covers none of the three rejection semantics.

## EIP-7702 breaks code size as an account-type oracle

[EIP-7702](https://eips.ethereum.org/EIPS/eip-7702) defines a transaction mechanism that
writes a delegation indicator to an EOA: `0xef0100 || address`. The specification states
that `EXTCODESIZE` sees the 23-byte indicator while calls execute the delegated code.

That means an address can have code and still be controlled by the EOA key that signs
ordinary application messages.

The old branch:

```text
codesize > 0 -> ERC-1271 only
codesize == 0 -> ecrecover only
```

can reject a valid ECDSA signature from a code-bearing EOA if the delegate does not expose
ERC-1271, reverts, or returns the wrong value.

A compatibility route is:

1. If code exists, attempt ERC-1271 in a failure-isolated static call.
2. If ERC-1271 returns exact magic, accept.
3. If it fails, apply the explicit canonical ECDSA policy.
4. Accept only if recovery equals the declared signer.

The included Vyper reference does exactly that:

```vyper
@external
@view
def verify(signer: address, digest: bytes32, signature: Signature) -> bool:
    if signer == empty(address):
        return False

    if signer.codesize > 0 and self._erc1271(signer, digest, signature):
        return True

    if signature.v != 27 and signature.v != 28:
        return False
    if convert(signature.s, uint256) > SECP256K1_HALF_N:
        return False

    recovered: address = ecrecover(
        digest,
        convert(signature.v, uint256),
        convert(signature.r, uint256),
        convert(signature.s, uint256),
    )
    return recovered == signer
```

This route does not accept because both paths were tried. It accepts only when one path
establishes the declared signer under its own rules.

The matrix includes both directions:

```text
code-bearing-eoa-ecdsa    accept  erc1271->ecrecover
code-bearing-eoa-invalid  reject  erc1271->ecrecover
```

The second case matters as much as the first. Fallback compatibility must not become
fallback permissiveness.

## ERC-6492: counterfactual validation is an explicit capability

A counterfactual smart account may have a predictable address before code is deployed at
that address. Ordinary ERC-1271 cannot validate it because there is nothing to call yet.

[ERC-6492](https://eips.ethereum.org/EIPS/eip-6492) defines a wrapper that carries a
factory or preparation call plus the inner ERC-1271 signature. The wrapper is identified
by a required 32-byte suffix. The specified verifier order checks that suffix before the
usual ERC-1271 and ECDSA paths, performs the deployment or preparation in a validation
context, then calls `isValidSignature`.

This is materially different from adding another pure signature decoder.

The verifier now handles caller-supplied target and calldata in a stateful preparation
step. Even when used through `eth_call` or a dedicated universal validator, that path has
a larger trust and gas surface. It needs target restrictions, failure isolation, resource
bounds, and a reviewed validator implementation.

For that reason, `vyper-sig-matrix` makes ERC-6492 opt-in:

```toml
[policy]
erc6492 = false
```

With the default policy, a valid-looking counterfactual wrapper is expected to reject.
Enable the feature and the expected route changes to an ERC-6492 universal validator.

The cells are:

```text
erc6492-counterfactual-valid  accept only when policy enables it
erc6492-factory-revert        reject
erc6492-inner-invalid         reject
```

Deployment success is not signature success. The inner wallet still has to return exact
ERC-1271 magic for the intended digest.

The small Vyper router included with this project intentionally does not implement
ERC-6492. That omission is labeled in its NatSpec. A minimal example should not smuggle a
universal deployment mechanism into code presented as a signature helper.

## ERC-7739: the same owner should not make every account interchangeable

Suppose one EOA controls several smart accounts. If each account validates the same raw
digest by recovering the same owner, a signature intended for one account can be replayed
against another unless the application or wallet adds another domain boundary.

[ERC-7739](https://eips.ethereum.org/EIPS/eip-7739) defines a defensive rehashing scheme
for ERC-1271 using nested EIP-712 typed structures. Its purpose is to prevent replay across
smart accounts while preserving readable typed signing requests.

That creates another policy dimension:

- `disabled` — no ERC-7739 behavior is expected;
- `optional` — nested signatures are supported, but legacy raw ERC-1271 remains accepted;
- `required` — raw digests are rejected; the nested, account-bound form is required.

The default example uses optional mode because a generic integration cannot assume every
wallet and signer already supports the nested format:

```toml
[policy]
erc7739_mode = "optional"
```

The generated cases include:

```text
erc7739-nested-valid      accept
erc7739-raw-digest        accept in optional mode, reject in required mode
erc7739-wrong-app-domain  reject
```

Enabling required mode before clients can construct and display the nested typed data is
a compatibility break. Leaving optional mode forever preserves the raw path and its
weaker replay boundary. The matrix makes the trade-off visible; it does not choose it for
the protocol.

## One policy file, twenty cases

The included example policy is:

```toml
version = 1

[policy]
erc1271 = true
erc6492 = false
erc7739_mode = "optional"
code_bearing_eoa_fallback = true
enforce_low_s = true
bind_chain_id = true
bind_verifying_contract = true
reject_zero_signer = true
```

Generate the matrix:

```bash
uv run vyper-sig-matrix generate \
  --policy examples/sig-matrix/policy.toml \
  --format markdown
```

The output contains twenty cases and a SHA-256 fingerprint of the normalized policy. The
fingerprint matters when evidence is generated in another job: results should be reviewed
against the exact policy that produced the expectations.

## Connect the matrix to the real verifier

The tool does not prescribe a test framework. A Titanoboa adapter can deploy the actual
Vyper verifier, wallets, and fixtures, run every generated case, then emit:

```json
{
  "results": [
    {
      "id": "eoa-valid-canonical",
      "observed": "accept",
      "path": "ecrecover"
    },
    {
      "id": "erc1271-revert",
      "observed": "reject",
      "path": "erc1271-staticcall"
    },
    {
      "id": "code-bearing-eoa-ecdsa",
      "observed": "accept",
      "path": "erc1271->ecrecover"
    }
  ]
}
```

Then check it:

```bash
uv run vyper-sig-matrix check artifacts/signature-results.json \
  --policy examples/sig-matrix/policy.toml
```

The full set must be present. Missing a negative case is a failure, not a skip disguised
as coverage. If an adapter reports a path, the path must match too. That catches a verifier
that reaches the right accept/reject outcome through an unintended permissive route.

## Fixtures should be hostile in specific ways

A useful smart-wallet fixture needs more than an owner and a valid signature.

Build separate behaviors for:

- exact magic in a normal 32-byte ABI response;
- wrong magic;
- revert;
- empty response;
- short response beginning with the magic bytes;
- magic returned only for one digest;
- expired session key;
- state-dependent authorization changed between quote and settlement;
- recursive external calls if the wallet architecture permits them.

For a code-bearing EOA, test at least:

- delegate supports ERC-1271 and returns magic;
- delegate lacks ERC-1271 but ECDSA is valid;
- delegate reverts and ECDSA is valid;
- delegate rejects and ECDSA is invalid;
- code changes between signed intent creation and execution where the execution model
  permits that state transition.

For ERC-6492, use an audited or deliberately constrained universal validator in the
integration harness. Test wrapper detection before ordinary signature parsing, factory
revert, wrong deployed address assumptions, preparation failure, inner wrong magic, and
gas bounds.

For ERC-7739, test the nested application domain, smart-account domain, content type, and
legacy compatibility mode separately.

One mock cannot represent all of these honestly. A matrix of small fixtures is easier to
review than one configurable wallet with twenty flags and unclear state.

## Verification order is policy, not an implementation detail

Order determines which parser sees attacker-controlled bytes and which acceptance route
wins when formats overlap.

For an integration supporting every feature discussed here, the high-level order is:

1. Reject an empty signer and malformed top-level encoding.
2. Detect the ERC-6492 suffix before ordinary ERC-1271 or ECDSA parsing.
3. If it is an ERC-6492 wrapper and policy allows it, validate through the trusted
   counterfactual path and require inner ERC-1271 success.
4. If code exists, attempt ERC-1271 through a static, failure-isolated call.
5. If exact magic is returned, accept.
6. If policy allows code-bearing EOA fallback, apply canonical ECDSA checks.
7. For code-free addresses, apply the same canonical ECDSA checks.
8. Reject every other path.

ERC-7739 sits in digest construction and smart-account validation policy rather than as a
last-minute signature fallback.

This order needs protocol-specific review. ERC-6492's specification explicitly says the
wrapper check precedes usual ERC-1271 and ECDSA validation, and warns against trying
`ecrecover` before ERC-1271 because contract signature bytes may also form a valid ECDSA
signature for a different address.

The matrix records the route because the route carries the security argument.

## What a matrix PASS does not prove

A PASS means the observed results covered every generated case and matched the selected
policy. It does not prove the ECDSA library is correct. It does not audit a wallet's
modules. It does not prove an ERC-6492 factory is safe. It does not prove the EIP-712 type
hash includes every value-bearing field.

The generated cases are a minimum compatibility baseline. Protocol-specific rows still
belong beside them:

- nonce already consumed;
- deadline boundary;
- partial-fill replay;
- chain fork;
- changed verifying contract;
- signer role revoked after signature creation;
- wallet upgrade between quote and settlement;
- batch isolation when one signature path fails.

The tool makes omissions visible. It cannot know every authorization invariant in a
protocol it has never seen.

## The public-good part

Signature support is often marketed as a list of standards: EIP-712, ERC-1271, 7702,
6492, 7739. Lists hide interactions. Matrices expose them.

The reusable artifact is a policy and a set of falsifiable cells:

- account state;
- signature encoding;
- wrapper;
- domain mode;
- expected decision;
- expected verification route.

Any Vyper DEX, permit system, vault automation layer, governance executor, or smart-wallet
integration can generate the same baseline and attach its own adapter. No KhomDev protocol
code is required.

That is the shift from a personal implementation note to a public security primitive.
The question is no longer “did one DEX accept one smart wallet?” The question is “which
account states and signature formats does this verifier accept, by which route, under
which explicit policy?”

Signatures are a compatibility matrix now. Ship the matrix with the verifier.

---

*Tool: `vyper-sig-matrix` in Vyper Scales. Python
3.12+, MIT licensed, no RPC, no signing, no broadcast. The included Vyper 0.4.3 router
compiles and covers ERC-1271 plus code-bearing EOA fallback; ERC-6492 deployment and
ERC-7739 rehashing remain explicitly outside that minimal contract.*
