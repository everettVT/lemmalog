# Large-Star / Small-Star evidence

The final driver completed with exit zero against server SHA-256
`3920135e89b973ac4b41dd153b60c006244ef51a65cdc9fa2055a1f07d2aba84`.
It registered a typed operator program, composed it through an ordinary wrapper,
and freshly compiled/activated one official DDlog/Differential graph. All 98
complete output comparisons matched an independent BFS oracle. No provider,
Python graph implementation, or simulated runtime supplied these results.

| Artifact | Scope |
| --- | --- |
| `real-backend-receipt.json` | Final outcome, backend identity, generated/native source and executable hashes, indexes into full observations |
| `rpc.jsonl` | Every driver tool call and returned result, in execution order |
| `snapshots.jsonl` | All 98 independently computed expected partitions and actual complete output partitions |
| `program.dl` | Exact generated composed source; its comments bind the native declaration/implementation hashes |
| `native-build.log` | Final official DDlog-to-Rust compiler and offline native build output |
| `agent-exchanges.json` | Separate author/reviewer agents using their own bridge subprocesses, with author disconnect, reviewer bridge insertion/merge, author reattach/bridge deletion/split, and shutdown |
| `first-run-summary.json`, `first-run.log` | Explicitly failed initial run: 97 graph comparisons and cleanup passed, then evidence copying used the wrong instance build path |
| `verification.json` | Test counts, provenance, raw/sanitized log hashes, limitations and sanitization record |
| `*-tests.log`, `rust-contracts.log` | Focused compiler/registry tests, independent oracle tests, and simulated-runtime host/MCP compatibility results |

The complete initial and final raw receipts, native executables, generated module
trees and build logs are retained locally outside the repository. The first-run
summary is a derived summary and records the complete raw receipt's hash. It is
not presented as a passing run. The collector was corrected and a minimum-vertex
removal case added; the final run performed a second fresh native compilation.
Production code and the backend binary were unchanged between those runs.
After verification, the driver's temporary root was changed from the macOS
`/private/tmp` spelling to portable `/tmp` and syntax-checked; its graph fixture,
assertions, evidence collection and production binary were unchanged.

The native implementation is the repository's
[`lemmalog_star.rs`](../../../src/ddlog/star/lemmalog_star.rs) and declaration
[`lemmalog_star.dl`](../../../src/ddlog/star/lemmalog_star.dl). Their exact hashes
are recorded with the compiled executable. The native dependency environment was
the retained official DDlog v1.2.3 distribution with offline Rust 1.65.0 assets.
The new local `types__lemmalog_star` package and its workspace dependency edges
were added to the supplied lock; no dependency download or third-party package
update was performed.

After the deterministic driver, two agents exercised a new owner using the
final run's source-and-executable-hash-verified native artifact. This was an
explicit cache reuse and performed no additional compilation. The author selected
and installed the exact existing wrapper version, seeded two components and an
isolated vertex, then closed its bridge. The reviewer independently verified
the instance/pin and rows, inserted bridge `(2,3)`, observed the merge, and closed
its own bridge. The author reattached, observed that change, deleted the bridge,
verified the split and unchanged isolate, then stopped the owner. Both owner and
native process were observed before stop and absent afterward; all bridges exited
zero and the descriptor/socket were removed.

41 focused Rust tests and 10 oracle tests passed. The 13 existing shared-host and
6 composition MCP compatibility tests also passed, using explicitly simulated
graph fixtures. These tests complement the native evidence; they do not establish
the algorithm's result. This change did not rerun the unrelated full memory
engine test suite or introduce CI wiring.

Published logs replace incidental local paths and omit color escapes/trailing
blank lines. Agent metadata omits the private
descriptor path and owner PID. Authored rules, generated source, fixture values,
RPC results, pins and output rows are preserved. The final receipt's raw hash and
published observation-file hashes bind the record.

This verification used a separate checkout and private build/socket directories.
The current host does not enforce an OS native-code sandbox; its child executes
with host-user privileges. MCP authors can configure only the vetted typed
operator and cannot upload native source. Program content versions, backend hash,
native implementation hashes and executable hashes identify different things.
See [requirements and gaps](../../large-small-star-requirements.md).
