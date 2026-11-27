# The seam is the security boundary

*A public testing pattern for Vyper systems that are correct contract by contract and
still fail when the contracts meet.*

---

The uncomfortable truth is that a green protocol test suite can prove the wrong system.

A vault can be correct. A router can be correct. A pool can be correct. Put the three
together and the first deposit can still revert because one side speaks six decimals,
another speaks eighteen, and the mock between them spoke a fictional language where
every token had the same units and every swap returned `dy = dx`.

That is not an edge case. It is the default shape of composition risk.

Most security work is organized around contracts: audit this vault, fuzz this engine,
verify this token. Production systems are organized around relationships. An output from
contract A becomes an input to contract B. A role granted in one repository controls a
function in another. An oracle value sampled here becomes a slippage floor there. The
joint carries assumptions that neither contract owns by itself.

That joint is the seam. The seam is the security boundary.

I built `seamcheck` to make those boundaries reviewable as data. It is intentionally
small: scan Vyper external-call sites, bind important calls to a manifest, state the
threat dimensions each seam must exercise, point at the evidence, and fail when the
evidence drifts or disappears.

The tool is public, offline, dependency-free, and not clever enough to invent confidence.
That last property matters most.

## Why contract coverage is not seam coverage

Consider a fee router that takes six-decimal USDC, swaps it into an eighteen-decimal
stablecoin, then sends the result into an emissions contract:

```vyper
@external
def route(dx_6dec: uint256, min_dy_18dec: uint256) -> uint256:
    return extcall IPool(self.pool).exchange(
        0,
        1,
        dx_6dec,
        min_dy_18dec,
    )
```

The router can have perfect statement coverage. The pool can have perfect statement
coverage. Neither number says whether this call is exercised with the real unit
conversion.

A friendly pool double often looks like this:

```vyper
@external
def exchange(i: uint256, j: uint256, dx: uint256, min_dy: uint256) -> uint256:
    return dx
```

It never charges a fee. It never slips. It never returns fewer units than requested. It
never reverts. Most importantly, it silently asserts that the input and output share one
scale.

The mock did not simplify the production system. It replaced the production system with
a different one.

That distinction explains why more fuzz iterations do not fix a bad neighbor model. A
fuzzer can generate ten million call sequences and still stay inside the world encoded by
the mock. If the mock says six decimals equal eighteen decimals, every generated sequence
inherits the lie.

Vyper makes external interactions unusually visible through explicit `extcall` and
`staticcall` syntax. The [language documentation](https://docs.vyperlang.org/en/stable/control-structures.html)
describes those calls as part of the contract interface. That visibility is useful, but
visibility is not coverage. A reviewer can find the call; a coverage manifest must still
state what can go wrong at it.

## A seam is a contract between contracts

The word “contract” is overloaded in smart-contract engineering. At a seam, it helps to
use the older meaning: a set of obligations shared by two components.

For an external call, those obligations usually span at least six dimensions.

### 1. Units

Raw integer values do not carry decimals in the EVM. `5_000_000` may mean five USDC,
five million wei-like units, five shares, or a basis-point-scaled ratio. The type system
sees `uint256` in every case.

A seam test should use unequal decimals on purpose. Equal decimals are a smoke test, not
evidence that conversion is correct.

### 2. Loss

Production interactions lose value to fees, price impact, rounding, spreads, and partial
fills. A test double that returns the ideal amount proves behavior in a zero-friction
economy.

An adversarial fixture should make loss configurable. The useful range starts at the
expected production fee and extends beyond it far enough to expose assumptions hidden in
the caller.

### 3. Failure semantics

Does the neighbor revert, return `False`, return no data, return malformed data, or return
a valid value outside the expected range? These are different paths.

For token calls, “revert” and “empty return” are not interchangeable. For an oracle,
“stale” and “revert” are not interchangeable. For ERC-1271, “call succeeds with the wrong
magic value” and “call reverts” are different observations even though both must reject
the signature.

The caller must define its response to each relevant class.

### 4. Time

An oracle, auction, vote, or signature can be valid at block N and invalid at block N+1.
Mocks frequently turn time-dependent state into a settable constant. That is convenient
for unit tests and dangerous as the only composition evidence.

A seam test should cross the boundary: just before expiry, exactly at expiry, just after
expiry, and after enough time for a moving average or checkpoint to drift.

### 5. Authority

A call can be safe while the role enabling it is too broad. If a router needs
`set_allocations` but receives a role that also gates `add_strategy` and `set_max_debt`,
the current router code is not the security boundary. The granted role is.

Seam evidence should test rejection at the access-control gate, not at a downstream
business assertion that happens to fail today.

### 6. Control flow

Callbacks, reentrancy, hooks, fallback behavior, and delegated execution all change who
controls the next instruction. A token that behaves like a passive ERC-20 in the fixture
cannot establish safety for a hook-bearing production asset.

The seam manifest should say when callbacks are out of scope. Silence is not a threat
model.

## Turn the threat model into a manifest

`seamcheck` uses TOML because the file needs to survive code review without a custom UI.
Here is the complete manifest for the decimal example:

```toml
version = 1

[project]
sources = ["contracts"]
strict_unregistered = true

[[seams]]
id = "fee-router.pool-exchange"
caller = "contracts/FeeRouter.vy"
target = "IPool(self.pool).exchange"
call_kind = "extcall"
risk = "high"
required = [
  "adversarial-neighbor",
  "decimal-mismatch",
  "lossy-output",
  "revert-path",
]
evidence = [{
  test = "tests/test_fee_router_seam.py::test_adversarial_pool_model",
  neighbor = "contracts/AdversarialPool.vy",
  covers = [
    "adversarial-neighbor",
    "decimal-mismatch",
    "lossy-output",
    "revert-path",
  ],
}]
```

Run it:

```bash
uv run seamcheck --manifest examples/seamcheck/seams.toml
```

The output is deliberately boring:

```text
seamcheck: PASS
  PASS  fee-router.pool-exchange [high] sites=contracts/FeeRouter.vy:14 evidence=1
```

Delete `revert-path` from the evidence and the command exits non-zero:

```text
seamcheck: GAP
  GAP   fee-router.pool-exchange [high] sites=contracts/FeeRouter.vy:14 evidence=1
        missing: revert-path
```

Rename the external method and leave the manifest stale; the seam becomes `ERROR`. Add a
new `staticcall` without registering it; strict mode reports an unregistered external
call and fails the gate.

This is not source-code coverage. It is threat-model coverage with source anchors.

## What counts as evidence

Evidence is not one ladder where every project must start at the top. It is a set of
different instruments that answer different questions.

### Real-neighbor test

Deploy the actual contracts on both sides in the same local EVM or on a fork. This is the
strongest evidence for ABI shape, decimal behavior, return encoding, access control, and
current implementation semantics.

It is also only evidence for the exact versions deployed. A fork test against yesterday's
pool says nothing about a newly upgraded pool unless the binding is pinned.

### Adversarial fixture

Build a small neighbor that is intentionally worse than the normal production case:
non-zero fees, lossy output, bounded liquidity, configurable reverts, stale values, and
malformed responses where the interface permits them.

This is stronger than a real-neighbor test for exploring conditions the live deployment
cannot cheaply reach. It is weaker for proving that the production ABI and internal
conventions were modeled correctly.

### Differential test

Drive the real neighbor and the fixture with the same inputs, then compare outputs or
invariants. This checks whether the fixture is conservative in the dimensions it claims
to model.

### Stateful composition test

Generate sequences across both contracts and assert a system invariant after every
step. Examples include conservation across a fee split, share-price monotonicity across
a strategy round trip, or “debt can only increase when the peg condition permits it.”

[Titanoboa integrates with pytest and Hypothesis](https://titanoboa.readthedocs.io/en/latest/tutorials/pytest/),
which makes this style natural for Vyper. The Vyper project's own style guide goes
further: it recommends property-based tests where logical and says compiler tests should
not involve mocking. That is a useful north star even when a DeFi repository still needs
fixtures for truly external systems.

No single evidence type subsumes the others. The manifest should say which one exists,
not compress them all into “covered.”

## The rule for mocks: never nicer without saying so

A friendly mock is not forbidden. It is useful for narrow unit tests where the neighbor
is irrelevant to the behavior under test.

The failure begins when friendly evidence is promoted into a system-level claim.

A practical classification is:

- **stub** — returns a fixed value so the caller can reach unrelated logic;
- **faithful fixture** — matches the documented neighbor behavior over a stated range;
- **adversarial fixture** — is at least as strict or lossy as production over a stated
  threat dimension;
- **real neighbor** — compiles and deploys the actual implementation;
- **fork binding** — talks to the actual deployed address at a pinned block.

Names matter because evidence gets weaker when categories blur. A fixture copied from a
real contract is still a fixture after the real contract changes. A fork is still a
snapshot after the chain advances. A mock with accurate decimals is still not evidence
for callback behavior.

`seamcheck` does not infer “real neighbor” from a filename. It will verify that a declared
neighbor file exists, but the manifest author owns the label. The tool refuses the more
dangerous convenience: silently upgrading a fixture into a production claim.

## A useful review loop

The shortest workflow that has held up for me is:

1. Scan every `extcall`, `staticcall`, and `raw_call`.
2. Register calls that cross a trust, repository, unit, or value boundary.
3. Write the invariant in units, not prose. For example:
   `usdc_in == tare_out * price / 1e12 + bounded_loss`.
4. List the threat dimensions that can falsify it.
5. Attach the smallest evidence for each dimension.
6. Add one real-neighbor or fork test for high-risk seams.
7. Keep the adversarial fixture for ranges the real deployment cannot reach safely.
8. Fail CI when source calls, required dimensions, or evidence paths drift.

The order matters. Starting with a test often leads to testing whatever the fixture
already makes easy. Starting with the seam invariant forces the fixture to earn its
place.

## What a PASS does not mean

`seamcheck` validates the relationship between four things:

- a declared call site;
- a required set of threat dimensions;
- evidence entries claiming to cover those dimensions;
- files that still exist at the declared paths;
- for a Python `path::node` selector, a function or class defined in that file.

It does not execute the evidence test. CI should do that separately. It does not inspect
the test and decide whether the test is honest, and it does not follow imports into other
modules. It does not prove that a fixture matches production. It cannot discover economic
assumptions that were never written down.

A call written with `extcall`, `staticcall`, or `raw_call` that the scanner cannot
classify is `UNASSESSED` and fails the gate. It is not treated as absent. The same failure
applies when a scanned file resolves outside the manifest directory.

A malicious author can write `covers = ["everything"]` beside an empty test. No static
format can cure a dishonest review process.

That limitation is why the report says exactly what a PASS establishes. The tool closes
the bookkeeping gap between threat model, source, and evidence. It does not pretend to
close the epistemic gap between a model and the chain.

## The public-good part

The useful artifact is not the scanner. A regex can find `extcall` in an afternoon.

The useful artifact is a shared language for seam evidence:

- decimal mismatch;
- lossy output;
- revert path;
- stale oracle;
- callback path;
- privilege boundary;
- real neighbor;
- fork binding.

Once those dimensions live in a manifest, a protocol can count what is actually covered,
review additions in a pull request, and hand an auditor a map of the joints that deserve
attention first. Another team can copy the format without copying any KhomDev contracts.

That is the change in direction I care about now. The old work asked, “what did one
personal stack survive?” This work asks, “what small artifact makes the next Vyper stack
harder to fool?”

A contract audit finds bugs in contracts. A seam manifest makes it harder to forget that
the production protocol exists between them.

The seam is where assumptions become money. Treat it as the security boundary.

---

*Tool: `seamcheck` in Vyper Scales. Python 3.12+, MIT
licensed, no RPC, no signing, no broadcast. The included example contains both the
friendly fixture that hides the decimal bug and the adversarial fixture that exposes the
relevant dimensions.*
