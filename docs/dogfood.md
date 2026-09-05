# Model-authored DDlog program exercise

This exercise asks whether a coding agent can compose and revise a small program
through the experimental MCP interface, without writing Rust or implementing the
computation in an imperative script. It is a single-session interface test, not a
comparison of swarm learning or a benchmark of incremental execution speed.

The author receives [a task](dogfood-task.md), [fixed inputs](dogfood-scenario.json),
and the [backend documentation](ddlog.md). It discovers the real server's tools,
authors two composed rules, submits transactions, changes the eligibility policy,
and inspects actual replies. A separate Python oracle computes the expected rows
and changes without calling Lemmalog, DDlog, or the authored program.

The scenarios cover duplicate inputs, alternative support, loss of the final
support, revision invalidation, and a policy replacement that must replay retained
facts. A malformed input and a build failure are deliberate operator injections;
they must not be presented as spontaneous mistakes by the author. Additional
supervisor transactions are labeled separately.

## Running the exercise

Prepare the offline DDlog build environment described in `ddlog.md`, with a unique
`LEMMALOG_DDLOG_WORKDIR` and `CARGO_TARGET_DIR`. Keep shared toolchain and vendor
inputs unchanged. Leave `LEMMALOG_AGENT_OPERATIONS` unset to exercise the original
four tools. A trusted build wrapper can consume a one-shot failure flag and return
nonzero before invoking `scripts/build-ddlog.sh` for the preservation check.

Launch the sequential relay in a terminal the author can interact with:

```sh
python3 scripts/ddlog_dogfood.py \
  --binary /absolute/path/to/lemmalog-ddlog-mcp \
  --session /absolute/path/to/new-session-directory \
  --actor author-task-reference
```

The author sends one JSON envelope per line, choosing its own tool arguments:

```json
{"stage":"discovery","method":"tools/list","params":{}}
```

The relay supplies transport IDs and records requests before sending them. It
preserves real responses, error flags, durations, the executable hash, and cleanup
observations in `events.jsonl`. It does not generate rules or tool calls. This is
MCP JSON-RPC over a terminal relay, not a native tool attachment to the model host.
The actor label is not authentication or proof of model authorship; preserve the
author's task trace as separate provenance. Host token usage is not inferred from
the JSON-RPC log.

The default limits are 80 calls, 600 seconds per call including transport writes,
1 MiB per request, and 4 MiB per response. The relay targets the experimental
sequential, response-only server; it is not a general asynchronous MCP client.
Compiler descendants share the server process group. Cleanup uses bounded probes
and escalation; an unavailable observation is never recorded as confirmed exit.

## Independent validation

Run the focused standard-library tests:

```sh
python3 -m unittest discover -s tests -p 'test_ddlog_dogfood*.py' -v
```

`scripts/ddlog_dogfood_oracle.py` provides a set-based reference join over current
revisions, findings, and support. It validates input changes atomically and parses
the selected output rows and signed changes strictly. The trace evaluator checks
the actual transaction sequence, program versions, replay counts, snapshots,
changes, and required failure preservation. A missing or incomplete trace cannot
establish successful completion.

Correct results establish that this particular authored program and these
transactions worked. They do not establish unrestricted language support, crash
durability, safe external retries, inference economics, or a learning advantage
over another agent with the same interface. Program changes still compile and
replay; incremental fact updates do not make compilation itself incremental.
