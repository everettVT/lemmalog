# Registered inference evidence

The original real driver at commit `409419e` passed on the first run: one freshly compiled official
DDlog/Differential graph, two actual GLM-5.3-Flash provider calls, 40 MCP tool
exchanges and seven complete-output comparisons against the independent set/join
oracle. The worker and server hashes were checked unchanged across the run.

Subsequent adversarial review found two worker failure-path defects outside that
original fixture. Both were reproduced before fixing them: a valid 950,000-byte
payload plus a valid 100,000-byte model response exceeded the combined completion
frame and lost the paid response; an empty successful settlement object was
incorrectly reported as completed. The corrected worker constructs and retains
the prepared response before local settlement checks, validates the exact request
identity, required booleans and transaction shape, and invalidates a pipe whose
completion acknowledgement is malformed. It does not retry the operation.

The corrected worker now passes **27 tests** (24 worker, 3 oracle), including
12 malformed acknowledgement cases and replay of all four acknowledgements from
the original real run through the corrected pipe validator. No additional
provider calls or native builds were performed for these fixes. The original
live receipts below remain unchanged and identify the original worker hash;
`review-verification.json` records the corrected source hash and test scope.
Before-fix failure logs and the final passing `review-regression-after.log`
preserve that distinction.

Revision 1's provider response completed and was held outside the graph.
Revision 2 then completed and was inserted first. Inserting revision 1 afterward
returned `fresh:false`; only revision 2 remained in both authored output
relations. Exact duplicate completions returned `duplicate:true`, while a
conflicting completion and duplicate claims were rejected. Replacing the owner
input changed the downstream join without another provider call. Reconnecting
the author retained the live state. All bridges and the host closed cleanly;
the descriptor and socket were removed.

| Requirement | Evidence and result |
| --- | --- |
| I1: configuration, operation and pin binding | Exact public configuration and distinct operation/program/instance hashes in `real-backend-receipt.json`; mismatch tests passed before real calls |
| I2: independent clients and bounded external work | Separate author/worker pipe connections; author queried the graph during provider call 1; controlled concurrency test reached and never exceeded two calls |
| I3: claim before provider | Both model calls followed committed claims; repeated claims rejected without another call |
| I4: current revision and stale retention | `snapshots.jsonl` records complete expected/actual rows before settlement, after revision 2, and after delayed revision 1; status and repeated stale completion prove retention |
| I5: idempotent completion | Exact repeats returned duplicate; conflicting output rejected; complete rows remained unchanged |
| I6: ordinary input rederivation | Owner changed from team-blue to team-green; same exact revision 2 text appeared in the new join; call count stayed two |
| I7: bounded failure and explicit uncertainty | 19 worker tests use controlled MCP/provider doubles for timeouts, failed transport, malformed envelopes, response limits, duplicate admission, process-group cleanup and retained prepared output after failed settlement |
| I8: real evidence and cleanup | Official generated source, native build log and executable hash retained; two distinct provider response IDs with finish reason stop; no cleanup errors |

Both provider responses used the configured model name and finished with `stop`.
They reported 115 and 118 total tokens respectively. The configured allowance
was 32,768 tokens with high reasoning; actual short responses reflect the small
synthetic fixture. This does not measure model quality, throughput, immutable
model weights or reasoning behavior.

| Artifact | Scope |
| --- | --- |
| `real-backend-receipt.json` | Configuration, operation/program pins, exact provider text and selected response metadata, source/backend/native hashes, checks and cleanup |
| `rpc.jsonl` | All 40 tool requests and returned results/errors, labeled author or worker |
| `snapshots.jsonl` | All seven full expected/actual authored output comparisons |
| `program.dl`, `native-build.log` | Exact generated source and sanitized official compiler/offline Rust build output |
| `real-run.log` | Native install and two provider-call milestones with final pass |
| `unit-tests.log` | 19 worker tests and 3 independent oracle tests, all passed |
| `verification.json` | Test scopes, raw and published hashes, environment and limitations |
| `review-verification.json`, `review-regression-*.log` | Reproduced review defects, corrected source/test hashes, 27 passing controlled tests and recorded-acknowledgement replay; no new live calls |

The actual run invoked the worker library's `dispatch` and `settle` methods to
control response ordering. The finite CLI's failure receipts and argument
contracts are covered by controlled tests. No provider or graph double supplied
the real run's results. No Rust server code changed, so the previously verified
merged server was reused; this increment did not rerun Rust tests or add CI.

Complete raw MCP receipts, native executable, generated project and logs remain
local. Published logs replace incidental host paths; synthetic inputs, outputs,
pins and tool results are preserved. The provider response hash covers the full
in-memory response body, but only content, model/response identity, usage and
finish reason are retained. Reasoning transcripts and credentials are not
recorded. The intentionally configured endpoint/model remain public evidence.

The original acceptance and corrected regression checks passed. The [documented
boundaries](../../inference-requirements.md) remain: session-local state, trusted
same-user clients, no durable delivery or automatic scheduling, no claimant
authentication, no remote cancellation or exactly-once guarantee, no uncertain
retries and no OS security sandbox.
