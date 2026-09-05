# Requirements: run Lemmalog on DDlog and Differential Dataflow

Goal: dogfood an MCP interface through which an agent authors, installs, runs,
inspects, and revises data-centric programs. Program definitions, input facts,
changes, results, and evidence are the interchange. DDlog compiles the program;
Differential Dataflow performs incremental computation; Timely supplies execution
and progress. Lemmalog contributes the starting language and interaction surface.

The central acceptance scenario is an actual agent calling MCP tools to define a
relational program, submit input changes, observe correct additions/retractions,
inspect why results hold, and revise the program. An agent need not generate a
bespoke imperative execution loop for every task. This does not imply that
external effects such as inference become pure relational operations.

Priority: requirements for that program-authoring workflow come first. Full
AgentMemory compatibility is a separate track, not a prerequisite to demonstrate
the goal. The memory-related inventory below records what adopting the existing
memory product would require; it must not expand the first milestone implicitly.

Discovery sources: `src/agent.rs` (AgentMemory, DEFAULT_RULES, snapshots),
`src/ast.rs` and `src/intern.rs` (language and values), `src/lib.rs` (rule
installation), `src/eval.rs` (membership, annotations, explanations, queries),
`src/semantics.rs` (relevance), and `src/bin/lemmalog-mcp.rs` (agent surface).
The initial `src/ddlog` adapter is a runnable foundation, not the completed memory
migration. Requirements below are proposed acceptance criteria; unchecked items
are not implementation claims.

## A. Architecture and ownership (memory extraction is a compatibility track)

1. Define a backend boundary below AgentMemory covering input mutation, rule
   lifecycle, logical time, evaluation completion, queries, evidence, and export.
2. Inventory direct access to Engine fields, interner, relations, and clocks;
   replace those accesses with the smallest useful backend operations.
3. Preserve extraction, episode management, context assembly, canonicalization,
   and other memory policy above that boundary.
4. Ensure the selected differential backend computes derived relations. Do not
   evaluate rules in the old engine and merely copy its outputs into Differential.
5. Retain the existing evaluator as a reference oracle during migration, with an
   explicit backend selection and no silent fallback for unsupported programs.
6. Specify which operations are synchronous completion boundaries and which
   return pending work. Keep model calls outside rule reevaluation.
7. Keep transport separate from backend behavior so library callers and MCP
   callers exercise the same semantic operations.

## B. Language and schemas

8. Maintain a versioned feature matrix for the Lemmalog syntax accepted by the
   DDlog lowering layer, with executable examples for every supported construct.
9. Reuse the existing parser where its semantics fit; introduce a typed
   intermediate representation between that AST and generated DDlog.
10. Preserve symbols versus signed integers, including mixed values in one column
    through a tagged value representation or another lossless encoding.
11. Specify escaping, Unicode, integer range, wildcard handling, repeated
    variables, arity, and variable binding. Reject invalid requests before mutation.
12. Preserve positive joins and projections, including multiple supporting
    derivations of the same output fact.
13. Support recursive rules and fixed-point completion; test cycles and deletion
    of the last remaining support, not only insertion into acyclic examples.
14. Preserve stratified negation and reject programs with recursion through
    negation before activating a replacement.
15. Preserve comparisons and arithmetic according to Lemmalog's actual type and
    overflow rules; do not inherit differing DDlog semantics accidentally.
16. Support count, min, max, and sum with explicit set/bag and empty-group
    semantics. Test their updates under deletions and alternative supports.
17. Lower `now(T)` to an explicit input relation or equivalent controlled value.
    Clock movement must cause the relevant derived changes.
18. Support inline facts used by bootstrap programs and tie their ownership to
    rule batches so uninstall removes only the appropriate assertions.
19. Preserve named rules and source spans or equivalent source references so
    compiler errors and evidence can point back to authored code.
20. Separate shape validation from semantic validation. Typed input schemas alone
    do not establish that a program is valid or equivalent.

## C. Rule lifecycle and compilation

21. Preserve append-style rule batches with stable identities and inspection of
    installed source; distinguish add, replace, and uninstall explicitly.
22. Recompile when a schema or rule change requires it; normal fact updates must
    not recompile or restart the running graph.
23. Build and validate a candidate program before replacing the active version.
24. Replay a consistent input snapshot into the candidate, wait for completion,
    and activate it at a defined boundary. Specify how concurrent writes are
    queued or included during the swap.
25. Failed parsing, validation, compilation, startup, or replay must preserve the
    previous program, facts, version, queryability, and explanation metadata.
26. Uninstalling a batch must retract unsupported derivations and retain facts
    supported by other batches. Include removal of the final installed batch.
27. Bind executable artifacts to source, schema, compiler/runtime versions, build
    configuration, and checksums. Cache reuse must validate that identity.
28. Establish a reproducible compiler toolchain and a supported platform matrix.
    The tested DDlog release currently needs a separate older Rust toolchain.
29. Bound compilation resources, surface diagnostics, and clean obsolete build
    artifacts without deleting active executables or retained evidence.

## D. Incremental state and progress

30. Define input set semantics, duplicate insertion, missing deletion, and update
    replacement. Differential multiplicities must not leak unintended duplicates.
31. Apply each accepted change batch transactionally and report completed deltas.
32. Retract an output only when no supporting derivation remains.
33. Expose a logical revision/frontier for completed reads and updates; an
    acknowledgement must identify which state it covers.
34. Keep unrelated keys or worlds isolated while dependent results update.
35. Distinguish submitted, computed, and durably published progress; a completed
    in-memory transaction is not a persistence acknowledgement.
36. Detect subprocess/compiler errors and broken streams explicitly. A pinned
    CLI protocol requires tests proving errors cannot pass its completion fence.
37. Define runtime failure recovery, cancellation, and timeout behavior. Do not
    continue serving possibly stale state as though the failed update succeeded.
38. Define query consistency during writes and program swaps before introducing
    parallel MCP sessions or workers.

## E. Provenance, confidence, and explanation

39. Preserve source episode identities and base fact annotations through lowering.
40. Match existing confidence combination: joins combine confidence, alternatives
    reconcile according to the existing evaluator's contract.
41. Preserve provenance union and correctly remove obsolete support after a
    source fact, rule, or episode is retracted.
42. Return fact-addressed explanations with named rules and source references.
    Direct rule variable bindings are a useful first slice, not full proof trees.
43. Specify finite explanations for recursive derivations and cycles.
44. Distinguish asserted facts, inferred facts, absent support, and unavailable
    evidence. Do not manufacture explanations in the MCP wrapper.
45. Test annotation-only updates where membership stays unchanged but confidence
    or provenance changes; downstream consumers must observe those changes.

## F. Memory compatibility track and reusable query behavior

46. Run the existing default temporal projection and exclusivity bootstrap on the
    differential backend without rewriting their domain meaning.
47. Preserve supersession, validity intervals, observation timestamps, and
    current-versus-historical memory behavior.
48. Preserve goal queries with constants, free/repeated variables, and predictable
    returned bindings. Whole-relation CLI dumps are only an initial interface.
49. Support hypothetical facts with no leakage into real state, clock, installed
    rules, or later queries; define the cost of the hypothetical branch.
50. Preserve canonicalization, alias conflict reporting, and retraction propagation.
51. Preserve retrieval/context assembly using equivalent facts, annotations,
    episodes, and budgets; retain replaceable embedding and extraction providers.
52. Provide change streams with precise additions, retractions, and annotation
    changes; document any compatibility mapping to existing Cleared events.
53. Evaluate demand-driven query support separately from full materialization;
    establish semantic equivalence before claiming performance equivalence.

## G. Persistence and recovery

54. Persist enough to recover base facts, annotations, episodes, clock, rule batch
    identities/source, schema version, and active program identity.
55. Define whether derived state is replayed or checkpointed and prove recovery
    yields equivalent queries and explanations.
56. Make save failures observable; successful in-memory mutation must not imply
    successful disk persistence when a save fails.
57. Define atomic publication of a consistent snapshot and behavior after partial
    writes, corrupt snapshots, and incompatible versions.
58. Keep request identity/retry semantics distinct from relation set semantics;
    a duplicate fact does not prove an external action was executed once.
59. Keep Parquet/Iceberg export optional and outside the initial backend migration.
    If added, bind its durable version to completed logical state explicitly.

## H. MCP and agent authoring

60. Preserve existing tool argument/result meaning when offering a compatible
    server. Use distinct names or an explicit version for changed contracts.
61. Publish operation-specific schemas, required fields, supported features,
    backend identity, and error categories agents can act on.
62. Return structured data alongside readable summaries for rows, deltas,
    versions, rule batches, and evidence; avoid requiring agents to parse CLI text.
63. Support a complete agent workflow: discover schema, author rule, validate,
    install, update facts, query, explain, revise, and remove the rule.
64. Treat structured tool arguments and grammar-constrained code generation as
    separate capabilities. A string field alone does not constrain program syntax.
65. If exposing AST generation, validate it and lower it through the same typed
    representation as textual programs; do not create two semantic implementations.
66. Keep inference requests and outcomes explicit if inference operations are
    added. Define identity, version, retry, stale-response, and cancellation rules.
67. Demonstrate at least one actual model-authored tool invocation end to end
    before claiming LLM constrained-generation integration.

## I. Evidence and rollout

68. Use the existing evaluator as an oracle on agreed semantics: memberships,
    confidence, provenance, queries, and rule lifecycle, including negative cases.
69. Verify the real compiled DDlog dependency graph and execute real MCP requests;
    mocks and source-only lowering tests must be labeled separately.
70. Include insert/delete, duplicate, alternative support, joins, recursive
    cycles, negation changes, aggregates, temporal advance, and unrelated-key
    isolation as their respective features become supported.
71. Test failed installation and runtime failure with the previous version still
    inspectable where promised; test restart recovery separately.
72. Measure compilation time, update latency, memory, replay time, and query
    latency separately, with workload and graph size recorded.
73. Require correctness parity for each migrated memory feature before switching
    it to the new backend by default. Performance claims need measurements.
74. Deliver incremental PRs with a feature matrix, runnable evidence, and named
    remaining requirements rather than treating the first adapter as the migration.

## Suggested implementation sequence

1. Executable program-authoring loop through MCP: real AST lowering, DDlog
   compilation, persistent Differential execution, input transactions, results,
   witnesses, replacement/replay, and explicit schemas.
2. Have an actual model author and invoke the tools to solve a relational task;
   exercise corrections and changed inputs, with independently checked outputs.
3. Expand language coverage required by those programs, structured results,
   grammar/AST generation, operational failures, and durable program identity.
4. Add external operations through explicit request/result relations where the
   domain requires them; keep scheduling and retry contracts explicit.
5. Separately migrate AgentMemory features if desired, using the compatibility
   requirements above rather than treating them as the first milestone.

The first stage has run locally in this PR's code. Model-authored MCP invocation
has not yet run. The sequence is proposed; later work follows the dogfooding
workflow, not memory-feature parity for its own sake.
