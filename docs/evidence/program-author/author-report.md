# Reviewer-evidence program author report

Completed all instructed phases through live MCP replies. The relay remains OPEN in exec session `SESSION_HANDLE`; no stop was issued. Raw exchanges and timings: `${RUNTIME_DIR}/baseline-session/events.jsonl`, author sequences 1–30.

## Authored programs

Initial program (`initial_install`):

```prolog
eligible(P,R,F) :- finding(P,R,F,S), S =< 2.
actionable(P,F) :- eligible(P,R,F), revision(P,R), support(P,R,F,U).
```

Revised program (`policy_change`, also submitted for `failed_build`):

```prolog
eligible(P,R,F) :- finding(P,R,F,S), S =< 3.
actionable(P,F) :- eligible(P,R,F), revision(P,R), support(P,R,F,U).
```

All fields are explicitly `int`. Input schemas: revision/2, finding/4, support/4. Output schemas: eligible/3, actionable/2. Variables bind project, revision, finding, severity, and support source; no fixture IDs are hardcoded in either rule.

## Observed results

I initialized the real server, discovered all four tools, authored each call in agent turns, and inspected each response before continuing. Each fixture phase was one transaction, followed by its own actionable query.

| Stage | Observed actionable (project, finding) | Version / evidence |
|---|---|---|
| initial_install | No facts loaded | Version 1; replayed_facts 0 |
| seed | (1,101), (2,201) | 1; rule-1 witnesses bind sources 501,503 |
| duplicate | (1,101), (2,201) | 1; empty deltas |
| alternate_support | (1,101), (2,201) | 1; source 501 witness retracted, source 601 added; no actionable delta |
| withdraw_last_support | (2,201) | 1; (1,101) and its witness retracted |
| restore_support | (1,101), (2,201) | 1; row and source-501 witness restored |
| revision_change | (1,103), (2,201) | 1; old-revision row/witness removed, new-revision row/witness added |
| policy_change | (1,103), (1,104), (2,201) | 2; replayed_facts 12, no manual reload |
| bad_mutation | (1,103), (1,104), (2,201) | 2; unchanged after error |
| corrected_mutation | (1,103), (1,104), (1,105), (2,201) | 2; source-506 witness added |
| failed_build | (1,103), (1,104), (1,105), (2,201) | 2; all four rule-1 witnesses unchanged |

After policy replacement I queried both witness rules: rule 0 included severity-3 findings 102 and 104, while rule 1 included only current-revision supported findings 103,104,201. This directly demonstrates the composed filter at that point. The baseline scenario replaces a support source in one transaction; it does not retain two distinct sources for one finding at a completed-transaction query boundary. Additional simultaneous-support coverage belongs to the supervisor's independent checks.

## Instructed negatives, separate from authoring mistakes

1. Submitted the supplied string severity `critical`. The tool returned `isError: true` and `Expected signed 64-bit integer`. A subsequent actionable query confirmed unchanged rows and version 2. Then I submitted the supplied integer correction plus its support and inspected its successful delta/query/witness.
2. Created exactly the authorized `${RUNTIME_DIR}/fail-next-build` flag with `touch`, then resubmitted the current valid program. The tool returned `isError: true`: `DDlog compilation failed; previous version retained`, with a build-log path. I read that log; it said `Operator-injected one-shot build failure for active-program preservation check`. The immediately following query and rule-1 witness call matched the pre-failure rows/bindings and still reported version 2.

These were supplied operator injections. Neither is evidence of a spontaneous model mistake or of discovering/recovering from an unplanned program error. This failed-build check exercised the supplied pre-compilation wrapper rejection; it does not establish behavior for every compiler/runtime failure mode.

## Unplanned errors and corrections

None observed. The first authored program installed successfully and all baseline responses matched the stated semantics. The only rule revision was the instructed threshold change from 2 to 3. No fixture data was changed to accommodate a program bug.

## Interface friction and timing

- The documented syntax and discovered argument schemas were enough to author this small positive, non-recursive program without a syntax repair.
- Results are JSON serialized inside MCP text content, with DDlog rows/witnesses again represented as strings. Positional output fields (`f0`, `f1`) require remembering schema order. This is readable at this scale but adds inspection/parsing work.
- Witnesses use numeric rule indices and direct bindings; rule 1 does not contain the upstream severity binding. I inspected rule 0 separately. No recursive proof tree or confidence provenance was supplied or inferred.
- Installation blocks without progress in its tool reply. Captured server round-trip time was 36.884 s for the initial compilation and 19.874 s for policy recompilation/replay. The injected pre-compilation failure returned in 0.0118 s. These use the supplied cached offline toolchain; they are not cold-install or general performance measurements.
- The malformed-value error identifies the required type but omits predicate, column, and offending value. This one-item fixture was easy to locate; larger batches would be harder to diagnose.
- The author made 30 JSON-RPC requests: 2 setup/discovery requests and 28 tool calls. Their recorded server round-trip times sum to 56.802 s. Session launch to the last author's response was 226.905 s; that includes agent/tool interaction gaps but excludes initial document reading and later report writing. These numbers are computed only from author sequences 1–30, not supervisor checks.

## Evidence boundaries

I read only the task brief, backend documentation, and supplied scenario for this exercise; I did not read the independent oracle implementation, its tests, or supervisor expected outputs. Agent task trace plus captured exchanges supports actual authorship; an actor label alone would not. A short post-run script summarized receipt timings only; it did not compute expected relation results or replay the workflow.

No server/Rust/relay/fixture/build-driver edit, dependency download, external inference request, or spending was performed. The only build-environment mutation was the instructed one-shot flag. The supplied process was kept open for independent supervisor checks.

This local trial demonstrates authoring and revising one composed reviewer-evidence program, incremental additions/retractions, retained-fact replay, direct witness inspection, typed-input rejection, and preservation under the supplied failed-build injection. It does not establish cross-agent learning, swarm advantage, durability, scalability, general language coverage, or unplanned-error recovery. Model token accounting was not supplied by the host, so no token-efficiency or dollar-cost claim is made.
