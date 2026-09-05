# Registered inference acceptance

This increment uses the existing typed registered-operation contract. A trusted
external worker calls one configured provider after claiming a request, then
submits its text as a factual response. DDlog evaluation never invokes HTTP.
There is no new MCP endpoint, native operator, dynamic code upload or composition
of effectful programs in this change.

The requirements and oracle below are defined before the real provider run.

| Requirement | Executable verification | Expected result |
| --- | --- | --- |
| I1. Bind explicit provider/model/prompt/sampling configuration to an immutable operation version and the installed program | Worker configuration and binding unit tests; real driver reads the pinned program and host operation registry | Configuration mismatch rejects before any provider call; receipts identify config, operation, program, server, generated source and native artifact separately |
| I2. External work uses independent pipe clients and bounded concurrency | Worker tests with controlled providers; real driver uses separate author and worker bridges | No PTY or graph lock spans a model call; at most the configured number of provider requests run |
| I3. Each admitted request is claimed before inference | Duplicate-claim tests and real driver | Second claim fails without another model call; exact operation/version/entity/revision/payload identifies the request |
| I4. Current output follows the latest revision when responses arrive out of order | Two actual provider calls: hold completed revision 1, complete revision 2, then submit revision 1 | Only revision 2 appears in complete output queries; stale revision 1 remains recorded and cannot replace it |
| I5. Duplicate completion is explicit and idempotent | Real driver repeats exact completion and submits a conflicting completion | Exact repeat returns duplicate; conflicting output rejects; neither invokes the provider |
| I6. Ordinary inputs can rederive downstream results without inference | Real driver changes an owner input joined with current agent_result | Complete output matches the independent set/join oracle using the exact provider text; model call count remains two |
| I7. Failure is bounded and uncertainty is preserved | Worker tests for timeout, malformed response, transport failure and invalid completion | No hidden provider/MCP retry, automatic reclaim or fabricated completion; errors name the next inspection action |
| I8. Evidence distinguishes real execution from doubles and records cleanup | Real driver plus unit-test logs | One real official DDlog/Differential compilation, two actual provider responses, retained raw artifacts, sanitized public fixture evidence, bounded bridge/owner cleanup |

Provider calls use the operator's already authenticated Modal CLI. Credentials
are neither part of authored definitions nor configuration hashes, logs or
receipts. Public configuration does not itself grant endpoint access. The
worker and CLI are trusted operator code; selecting their executable is not an
interactive program-author capability.

The provider is not a deterministic function: a pinned endpoint/model name and
configuration do not prove immutable model weights or reproducible output.
Receipts record what the endpoint actually returned. This is a protocol test,
not an inference quality or throughput benchmark.

Claims, request records and completed text remain session-local. There are no
leases, durable queue, crash recovery, cancellation, claimant authentication or
exactly-once provider guarantees. Same-user attached clients have full access.
An interrupted or uncertain provider call remains claimed until an operator
reconciles it; the worker must not retry or invent a failure response. A private
worktree/socket directory is not an OS security sandbox. Native/operator code
changes still require reviewed versioned repository changes and dedicated tests.
