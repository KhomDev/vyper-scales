# A compiler upgrade is a protocol migration

*A reproducible Vyper upgrade gate built from compiler artifacts, storage layout, and
execution traces—not confidence in a changelog.*

---

Changing a smart-contract compiler changes the program that creates the bytecode that
holds the money.

Treating that as a dependency bump is the wrong mental model. It is a protocol migration
with a new code generator in the trust boundary.

The source may be identical. The runtime bytes can change because the optimizer changed,
the default EVM version changed, metadata changed, an ABI edge was fixed, storage layout
logic changed, or code generation took a different path. Most of those changes can be
legitimate. Some are exactly why the upgrade is desirable. None should be accepted on
faith.

Release notes answer “what did maintainers intend to change?” A migration gate has to
answer a different question: “what changed for this protocol, under this build
configuration, over the behaviors that matter?”

I built `vyper-semantic-diff` around that distinction. It captures Vyper compiler output,
normalizes the parts that define compatibility, compares execution traces, and classifies
bytecode drift separately from interface or behavior drift.

It also refuses to call an artifact-only comparison “semantic.” If neither side contains
replay traces, the default verdict is `UNASSESSED`, not `PASS`.

## Why “same source” is not the invariant

The naive upgrade test is:

```text
old compiler + source -> old bytecode
new compiler + source -> new bytecode

old bytecode != new bytecode
```

That result is expected often enough to be useless by itself. A compiler upgrade that
never changes bytecode did not need a new compiler.

The opposite result is not sufficient either:

```text
old bytecode == new bytecode
```

Equal bytes are strong evidence for that exact build, but the check can still be attached
to the wrong source, wrong import tree, wrong optimization setting, or wrong deployment
artifact. Equality without provenance can compare two copies of the same mistake.

The useful invariant is layered:

1. The intended source and import tree were compiled under explicit settings.
2. The external interface did not change unintentionally.
3. Function selectors did not drift.
4. Storage layout did not drift for state that must remain compatible.
5. The protocol produced equivalent observable behavior over a reviewed replay corpus.
6. Any remaining bytecode change is recorded as expected evidence, not ignored noise.

That is a migration receipt.

## Pin the build dimensions first

A compiler comparison is meaningless unless both sides identify the build.

At minimum, capture:

- compiler executable and exact version;
- source hash;
- import root or archived dependency tree;
- EVM version;
- optimization mode;
- experimental code-generation flags;
- storage-layout overrides;
- metadata settings.

This is not theoretical bookkeeping. Vyper's [v0.4.3 release notes](https://docs.vyperlang.org/en/stable/release-notes.html)
list a default EVM-version change to Prague and improvements to the Venom optimizer
pipeline. If a comparison leaves `--evm-version` implicit, it can accidentally test an
EVM migration at the same time as a compiler migration. If it leaves optimization
implicit, it can test a code-generation policy change without naming it.

The capture command makes those choices explicit:

```bash
uv run vyper-semantic-diff compile src/Vault.vy \
  --compiler .compilers/vyper-0.4.3/bin/vyper \
  --project-root . \
  --evm-version prague \
  --optimize gas \
  --traces artifacts/0.4.3-traces.json \
  --output artifacts/vault-0.4.3.json
```

Repeat with the candidate compiler. Do not reuse an unversioned `vyper` on `PATH` and
trust that the environment stayed still.

For pre-release compilers, the bar should be higher. Vyper's
[versioning guideline](https://docs.vyperlang.org/en/stable/versioning.html) defines
alpha builds as work in progress, beta builds as work intended for release, and release
candidates as the stage that precedes a major release audit. That does not mean an alpha
cannot be evaluated. It means “the source compiles” is the start of evaluation, not a
shipping signal.

## Layer 1: ABI shape

The ABI is the public language other contracts, bots, frontends, and indexers speak.

The diff normalizes each entry into a canonical key such as:

```text
function:deposit(uint256,address)
event:Deposit(address,address,uint256,uint256)
error:Unauthorized(address)
```

For functions it compares mutability and output types. For events it also compares which
inputs are `indexed`. For tuple inputs it recursively canonicalizes component types. A
renamed input parameter does not matter to the selector; a changed tuple component does.
An omitted ABI, selector map, storage layout, or runtime bytecode is an error, not an
empty match. Duplicate ABI signatures are an error.

ABI drift can be intentional. A new view function may be backward compatible. A removed
function, changed output, or mutability change may not be. The tool currently classifies
all ABI drift as breaking by default because a generic analyzer cannot know every
downstream consumer.

That conservative default is cheaper than discovering after deployment that an off-chain
solver decoded a return value under the old shape.

## Layer 2: method identifiers

Function selectors are only four bytes. They are also the dispatch surface for every
external call.

Vyper exposes `method_identifiers` in `combined_json`. The diff compares the complete
signature-to-selector mapping directly:

```json
{
  "deposit(uint256,address)": "0x6e553f65",
  "totalAssets()": "0x01e1d114"
}
```

This catches a signature change even if a generated ABI consumer happens to tolerate it.
It also catches changes caused by default arguments, where Vyper may generate multiple
selectors. The [Vyper function documentation](https://docs.vyperlang.org/en/stable/control-structures.html)
calls out that an external function with default arguments produces `N+1` selectors.

Selector stability is not the same as semantic stability. It is a necessary compatibility
check, not the final verdict.

## Layer 3: storage layout

For a fresh immutable deployment, layout drift may be acceptable if every state value is
initialized from scratch. For a proxy, blueprint pattern, migration script, or any system
that preserves storage while code changes, layout drift can be catastrophic.

The diff compares Vyper's `layout` output as structured JSON. A changed slot, offset,
type, or variable order fails the default policy. Creation bytecode and a recorded
integrity string are informational unless policy opts in. The absolute compiler path is
recorded and is not itself a difference; version, EVM version, optimizer, and the
compiler's own settings are.

That is intentionally blunt. An advanced migration may move state safely through an
explicit transformation. In that case the right artifact is not an allowlist that hides
the difference. It is:

1. the red storage diff;
2. the migration function or script;
3. a pre-state fixture;
4. the post-migration state trace;
5. an explicit policy decision accepting the planned change.

The red diff is part of the receipt. Turning it green would erase the reason the migration
test exists.

## Layer 4: execution traces

This is where an artifact diff becomes a semantic differential.

A trace is a small, tool-neutral JSON record of one reviewed behavior:

```json
{
  "case": "withdraw-after-loss",
  "success": true,
  "return_data": "0x...",
  "events": [
    {"name": "Withdraw", "assets": "950000", "shares": "1000000"}
  ],
  "state": {
    "total_assets": "9000000",
    "total_supply": "9473684"
  },
  "balances": {
    "vault_usdc": "0",
    "receiver_usdc": "950000"
  },
  "gas_used": 118204
}
```

The harness that produces the trace can be Titanoboa, Moccasin, a fork runner, or another
EVM tool. `vyper-semantic-diff` does not own the execution engine. It owns the comparison
contract.

By default it ignores gas and execution-time fields on the trace object itself because
optimizer improvements are expected to move them. Nested fields keep those names if a
protocol uses them for state. It compares success vs revert, return data, event content and
ordering, selected state, balances, and any other captured field. A trace that contains
only a case name and ignored fields is unassessed.

The same replay corpus runs against both compiler artifacts. If `withdraw-after-loss`
returns 950,000 units under the baseline and 949,999 under the candidate, the report says
which case diverged. It does not decide whether one unit is acceptable. That decision
belongs in a reviewed normalization or tolerance policy, not in an unlogged shrug.

## Choose traces that can falsify the migration

A happy-path trace suite is a demo. A migration corpus needs behaviors that exercise the
compiler and protocol boundaries.

For a Vyper DeFi system, useful cases include:

- arithmetic at zero, one, maximum safe input, and one step beyond a bound;
- every rounding direction where shares and assets convert;
- empty and maximum-length dynamic arrays;
- default arguments and every generated selector;
- failed and successful `extcall`, `staticcall`, and `raw_call` paths;
- short, empty, malformed, and oversized return data where raw calls are used;
- reentrancy-lock behavior across external callbacks;
- storage reads and writes around packed or overridden slots;
- event ordering when multiple external calls occur;
- revert class and state rollback after a failed neighbor call;
- stateful sequences, not only isolated calls;
- fork replays against pinned production neighbors for high-risk seams.

The Vyper documentation recommends pytest with Titanoboa or Brownie for contract tests,
and [Titanoboa supports pytest and Hypothesis](https://titanoboa.readthedocs.io/en/latest/tutorials/pytest/).
That is enough to build a compiler differential without inventing a second testing stack.

The important part is serialization. A trace that only exists as a green assertion cannot
be inspected across compilers. A compact JSON receipt can.

## Read the report by category

The included example compares two artifacts with identical source metadata, ABI,
selectors, storage, and behavior. Runtime bytecode and gas usage differ.

```bash
uv run vyper-semantic-diff compare \
  examples/semantic-diff/baseline.json \
  examples/semantic-diff/candidate.json
```

Output:

```text
vyper-semantic-diff: PASS
  behavior: PASS (2 cases)
  INFORMATIONAL bytecode:runtime
      baseline:  "0x6001600055"
      candidate: "0x5f600155"
  INFORMATIONAL compiler:metadata
      baseline:  {"evm_version": "prague", "optimize": "gas", "version": "0.4.3"}
      candidate: {"evm_version": "prague", "optimize": "gas", "version": "0.5.0a3"}
  note: runtime bytecode changed; informational unless policy fails on bytecode
  note: compiler metadata changed; informational unless policy fails on compiler
```

This is the expected shape of a compiler migration: bytes and compiler metadata changed,
specified compatibility surfaces did not, and reviewed traces stayed equal. The runtime
bytes in this fixture are illustrative. The storage layout and source hash match the
included `Counter.vy` contract.

Remove both trace sets and run again:

```text
vyper-semantic-diff: UNASSESSED
  behavior: UNASSESSED (0 cases)
  note: no execution traces were present on either side
```

The command exits `3`. It does not confuse “no observed difference” with “behavior was
compared.”

Change one state value in one trace and the result is `FAIL`. Change an ABI output and the
result is `FAIL`. Change only gas and the default result remains `PASS` because gas is
explicitly outside the semantic equality policy.

## The policy file is part of the audit surface

The default policy is:

```toml
[policy]
fail_on = ["abi", "selectors", "storage", "traces"]
ignore_trace_fields = ["gas", "gas_used", "execution_time_ns"]
require_traces = true
```

A team can fail on bytecode too. That is useful for reproducible-build checks where any
byte drift is unexpected. A team can set `require_traces = false` for a narrow artifact
gate, but the behavior status remains `UNASSESSED` in the report.

Policy changes deserve the same review as contract changes. Adding `events` to ignored
fields can hide a real indexer break. Removing storage from `fail_on` can turn an unsafe
upgrade into a green job. The fastest way to corrupt a security tool is to make its policy
file look like harmless CI configuration.

## A staged upgrade process

The migration I would use for a money-bearing Vyper protocol is:

### Stage 0: freeze provenance

Archive the current compiler, settings, source hashes, imports, and deploy artifacts before
touching the candidate environment.

### Stage 1: compile-only inventory

Compile every target with both versions. Record failures, warnings, ABI, selectors,
layout, runtime bytes, and integrity output. Do not edit source yet. Compilation failures
are migration requirements, not inconveniences to patch blindly.

### Stage 2: deterministic replay

Run the same unit, boundary, stateful, and seam corpus against both builds. Export traces
from the same seeds and initial state.

### Stage 3: classify every difference

Mark each difference as intended, tolerated with a quantified bound, or blocking. “Looks
fine” is not a category.

### Stage 4: fork rehearsal

For a deployed system, replay the candidate against a pinned fork. Verify roles, immutable
bindings, storage, balances, oracle responses, and external return behavior.

### Stage 5: independent review

Review the compiler release notes, known advisories, migration diff, trace corpus, and
policy changes. The person who changed the source should not be the only person deciding
that a divergence is harmless. A solo engineer can approximate independence by separating
the implementation and review sessions and preserving machine-readable evidence.

### Stage 6: deploy and verify

Only after the migration receipt is complete should deployment enter scope. Recompile
from the pinned environment, compare the deployment artifact, and verify the on-chain
runtime and configuration after broadcast.

The semantic diff does not authorize Stage 6. It produces evidence for the decision.

## What the tool cannot prove

Differential testing is bounded by the inputs it executes. Two compilers can agree on
every captured case and diverge on the next one. Identical traces can hide internal gas
changes, memory behavior that does not reach the selected observation, or a path the
corpus never calls.

The tool also does not prove that the baseline compiler was correct. It treats baseline
behavior as the migration reference. If both versions share a bug, equality preserves the
bug perfectly.

Formal compiler verification, independent test generation, metamorphic testing, and
differential fuzzing across more than two implementations can provide stronger evidence.
They do not make the small receipt useless. They make its boundary clearer.

The claim is narrow:

> Under these pinned builds, over these compatibility surfaces and these replay cases,
> the candidate either matched, diverged, or was not assessed.

That sentence is honest enough to ship in a report.

## The public-good part

Compiler-upgrade advice is usually a checklist. Checklists are useful and easy to forget.
A JSON artifact, a trace schema, a policy file, and a non-zero exit code are harder to
forget.

The useful public artifact is not a promise that one Vyper version is safe. It is a
repeatable way for any Vyper repository to ask the right migration question of any two
compiler builds.

The compiler is inside the protocol's trust boundary whether the architecture diagram
shows it or not. Upgrade it with the same discipline used for a vault implementation, an
oracle, or a governance module.

A dependency bump updates a tool. A compiler bump can update every executable instruction
that users trust with money.

Treat it as a protocol migration. Keep the receipt.

---

*Tool: `vyper-semantic-diff` in Vyper Scales. Python
3.12+, MIT licensed, no RPC, no signing, no broadcast. The capture command executes only
the compiler argument vector supplied by the operator and never uses `shell=True`.*
