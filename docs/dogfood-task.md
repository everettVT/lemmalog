# Model-authored reviewer-evidence program

This exercise tests one agent authoring and revising a small relational program
through the experimental MCP interface. It is not a swarm comparison. Fixtures
and injected errors are supplied by the operator; the agent must author the rules
and tool calls. The independent oracle is not available to the author.

Use the four tools discovered from the running server. Read `docs/ddlog.md` for
language and tool limitations. Do not edit Rust, the server, relay, oracle, build
driver, or fixtures. Do not read the oracle implementation or its tests. Do not
generate an imperative implementation of the computation or a script that blindly
replays all tool calls. Make calls in your agent turns and inspect their responses.

The interface uses these fixed schemas (all fields are `int`):

| Relation | Input? | Fields in order |
|---|---|---|
| revision | yes | project, revision |
| finding | yes | project, revision, finding_id, severity |
| support | yes | project, revision, finding_id, source |
| eligible | no | project, revision, finding_id |
| actionable | no | project, finding_id |

Initially, a finding is eligible when severity is at most 2. An eligible finding
is actionable if its revision is current and at least one matching support exists.
Compose these as separate eligible and actionable rules. Multiple support sources
must not duplicate actionable rows. Inserting an existing input is a no-op.

1. Initialize the MCP connection and discover the tools. Install your own program
   using stage `initial_install`. No project/finding IDs may be hardcoded in rules.
2. Apply phases `seed` through `revision_change` from `dogfood-scenario.json`, one
   transaction per phase. Use its phase ID as the relay stage. Query actionable
   after each transaction and inspect witnesses where useful. Do not alter the
   fixture data to accommodate a program bug; correct your rules if necessary.
3. The requirement now changes: severity at most 3 is eligible. Install the revised
   program using stage `policy_change`. Do not manually reload facts. Query the
   results and inspect the reported replay count and program version.
4. Submit the `bad_mutation` fixture, an intentionally malformed operator input.
   Record the tool error and check that results/version are unchanged. Then submit
   `corrected_mutation`, followed by an actionable query. These are injected errors,
   not evidence of a spontaneous model mistake.
5. For a controlled failed-build check, create the supplied
   `/private/tmp/lemmalog-agent-dogfood-runtime/fail-next-build` flag. This is the
   only permitted build-environment mutation. Record this operator-requested
   injection in your report. Reinstall your current valid program with stage
   `failed_build`. The wrapper will reject that one build before compilation.
   Inspect the error; query rows and witnesses to confirm the prior version remains.
6. Report your authored program, any unplanned authoring errors and corrections,
   tool/interface friction, and what the observations establish. Keep the session
   open and send its exec session ID to the supervisor for independent checks.

The supervisor may run additional labeled oracle checks against your final program.
Do not issue a stop until asked. The relay supplies transport IDs only. An input
line looks like `{"stage":"discovery","method":"tools/list","params":{}}`.
All real exchanges and timings are retained in the session directory. Agent
authorship is additionally supported by the agent task trace, not an actor label
in a JSON file. Compiler time is included; model token accounting is unavailable
unless independently supplied by the model host.
