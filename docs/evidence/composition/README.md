# Composition and lifecycle evidence

The [requirements checklist](../../composition-requirements.md) is verified by
focused registry/interface tests and actual DDlog graphs. The production server
used throughout has SHA-256
`5f0cd0d0d625a4df30a30ac394f9b0956b354c998ee96fc7b94cffee9ec69795`.

| Evidence | Result and scope |
|---|---|
| [verification.json](verification.json) | Complete final Rust suite: 102 tests passed, including 17 registry and 13 composition contracts. Six MCP composition/lifecycle cases and 13 shared-owner cases passed with explicitly simulated runtimes. |
| [native-build-evidence.json](native-build-evidence.json) | Five native compilations using the official DDlog distribution and retained offline toolchain: three individual programs, the nested program, and its updated version. Includes source, executable and raw build-log hashes. |
| [real-backend-receipt.json](real-backend-receipt.json) | Successful deterministic acceptance: 14 grouped checks, 20 exact expected/observed snapshots, five real graphs. Reuses the five source/executable-verified native artifacts described above. |
| [agent-exchanges.json](agent-exchanges.json) | Separate author/reviewer agents attach using fresh pipe bridges. Reviewer independently reads the exact pin and inserts three upstream facts; author reattaches and observes the resulting row, then explicitly stops both processes and removes endpoints. Uses the same verified native artifact. |
| [fixture.json](fixture.json) | Synthetic integer inputs and mutations. The independent oracle is [composition_oracle.py](../../../scripts/composition_oracle.py), a finite set/join implementation. No provider calls or model-inference results are claimed. |

The driver first validates and runs severity filtering, current-revision
selection, and support joining independently. A saved program then references
all three exact versions, and a wrapper references that composed program through
its ordinary interface. The fourth and fifth native graphs are these nested
program versions. Three private `scratch` relations remain distinct in the
actual generated source. Mutation cases cover duplicate insertion, removing one
of multiple supports, removing the last support, restoring support, revision
advance, upstream retraction and restoration. A fresh reviewer client and
archive/restore transitions preserve the same live program pins and expected
rows.

The initial native run completed all five compilations and graph/pinning checks,
then exposed a driver assertion error. Search deliberately matches authored
references, so searching an archived identity also returns active programs that
reference it. The driver had incorrectly expected the entire result page to be
empty. The correction checks absence of that specific archived identity.
Returned identities/status and the documented substring semantics were enough to
repair it; no product diagnostic endpoint was needed. A failure-copy helper was
also corrected to preserve symlinks and skip live Unix sockets.

The [partial receipt](native-first-pass-partial-receipt.json) deliberately retains
`passed: false`; the [sanitized failure log](native-first-pass.log) preserves the
failure. After those driver-only fixes, the complete scenario passed using
exact-source and executable-hash checked native artifacts, with **zero additional
native compilations**. [cached-completion.log](cached-completion.log) records that
successful run. Pure validation, native compilation, cached executable reuse, and
simulated transport tests are distinct evidence scopes. The successful driver
also checks compiler/backend command bytes at start and finish. Its optional
expected-server-hash argument and command lookup were subsequently made portable;
those changes do not alter the scenario.

Raw native executables, generated sources and complete build logs are retained
outside the repository. Published evidence contains synthetic fixtures and no
incidental host paths; only the native failure log needed path substitution.
Original and sanitized log hashes are recorded in `verification.json`. Generated
source and executable hashes remain unchanged.

To repeat with the official DDlog environment configured as in
[ddlog.md](../../ddlog.md):

```sh
cargo test --features mcp
cargo build --features mcp --bin lemmalog-ddlog-mcp
python3 -m unittest discover -s tests -p test_composition_mcp.py -v
python3 -m unittest discover -s tests -p test_shared_host.py -v
COMPOSITION_RECEIPT=/absolute/receipts/composition.json \
COMPOSITION_ARTIFACTS=/absolute/receipts/composition-artifacts \
  python3 scripts/test-composition.py
```

The driver normally performs five native compilations sequentially. The optional
`COMPOSITION_EXPECT_SERVER_SHA256` fixes an expected server identity; start/end
identity checks always run. The receipt reports verified artifact reuse only when
an operator explicitly supplies the corresponding native-build evidence and a
hash-checking build driver. There is no hidden runtime replay or automatic retry.

This fixture verifies program composition and lifecycle semantics. It does not
implement or validate LARGE-STAR/SMALL-STAR connected components, general
recursion, or external-effect routing through composed programs.
