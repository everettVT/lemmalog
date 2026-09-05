# Actual program authoring through the four MCP tools

**Passed this bounded interface exercise.** A Codex agent authored and revised
two composed rules, operated the real MCP server, and inspected its replies.
The official DDlog compiler generated programs that ran on Differential/Timely.
The independent Python oracle matched the recorded outputs, signed changes, and
direct witnesses. This is not evidence of faster learning or swarm superiority.

The [author report](author-report.md) preserves the authored programs and
step-by-step observations. The [sanitized exchanges](events.jsonl),
[machine verification](oracle-report.json), and
[negative oracle checks](negative-oracle-checks.json) support the result.

| Evidence | Result |
|---|---|
| Actual calls | 30 author calls, then 6 separately labeled supervisor calls |
| Program installation | Initial version 1; policy replacement version 2 replayed 12 facts |
| Independent output checks | 10 signed change sets and 13 snapshots matched |
| Independent witness checks | 7 sets of direct factual bindings matched |
| Instructed failures | Wrong-type input and injected build rejection preserved active state |
| Extra data | Simultaneous supports, multiple revisions, project isolation, threshold boundary |
| Final state | Version 2, 14 retained facts, four actionable findings |
| Cleanup | Server exit 0; process-group disappearance confirmed |

The author wrote this initial program without a syntax repair or an unplanned
tool error:

```prolog
eligible(P,R,F) :- finding(P,R,F,S), S =< 2.
actionable(P,F) :- eligible(P,R,F), revision(P,R), support(P,R,F,U).
```

The requirement change raised the threshold to 3. The author did not reload
facts. The malformed input and failed build were operator-supplied tests, not
mistakes discovered by the model. The build injection rejected the candidate
before compilation; it does not cover all compiler or runtime failures.

The supervisor supplied additional unseen data after authoring was complete.
Those calls were delegated to the same agent because its live terminal session
was accessible only from that agent. A long terminal input line required recovery
before submission; the complete transaction was delivered once. The
[separate execution report](supervisor-probe-execution.md) records that distinction.

## Reproduce the evidence check

From the repository root:

```sh
python3 scripts/check_ddlog_dogfood_trace.py \
  --events docs/evidence/program-author/events.jsonl \
  --scenario docs/dogfood-scenario.json
```

The checker reads receipts, not the backend. It validates transaction coverage,
versions, retained-fact counts, and exact expected relation contents. It also
checks the requested two-rule structure without requiring an exact source string.
Two root-generated negative checks injected a stale output row and removed a
required retraction; both were rejected. These are evaluator checks, not extra
runtime trials. The author did not read the oracle or its tests.

Backend executable SHA-256:
`e8dceab1fb34bc7d09a58d86a08639e56f5586abacc643e3cfa6aa81969115ff`.
Backend source: `0317f0a4e5ae3adc05b40b89b3369d22bdd2f1d6`.
The peer verified the retained binary against its clean committed source; this
task verified the copied hash and did not rebuild the MCP server independently.
The original four tools were selected by leaving the operation registry unset.

[Provenance](provenance.json) records the relay, oracle, task, fixture, toolchain
inputs, and generated executable hashes. Generated DDlog sources and build logs
are retained here; large executables and generated Rust remain in the local
runtime directory. Operator scripts record the exact local offline environment
and use path variables for another machine.

## What this teaches about the interface

The rule language was sufficient for this small composition. Inspection was more
awkward than authoring: results are nested text with positional fields, errors
omit the input field, explanations use numeric rule indices, and installation
waits without progress. Structured named rows, precise field errors, stable rule
identifiers, and compilation progress are concrete improvements to consider.

The two successful installation round trips were 36.884 and 19.874 seconds using
the prepared offline toolchain. These are observations, not a performance
comparison. Host model token usage was unavailable; no separate inference API
was called. The exercise does not establish token or dollar efficiency.

This provides evidence for agent-authored composition, incremental maintenance,
and bounded state-preservation behavior. It does not establish durability,
arbitrary DDlog language support, constrained model generation, safe external
retry semantics, scalability, or longitudinal learning. Archetype integration was
not part of this test. Ordinary agents should receive the same interface in a
future swarm comparison.

## Publication sanitization

The exact local receipts remain unchanged outside this publication branch. This
copy replaces temporary checkout/toolchain/runtime paths and build-session names
with named placeholders, removes the server PID, and replaces task references and
terminal handles with role labels. Requests, facts, rules, returned rows, signed
changes, versions, errors, and timings are otherwise preserved. The independently
scored report is regenerated against this sanitized trace. `sanitization.json`
links the source trace hash with the published trace hash. Provenance hashes of
original run inputs still refer to those original local inputs; `manifest.json`
checks the published files. No user data or model-provider credentials were used.
