# Actual Codex author and worker through MCP

A separate Codex agent authored the program in `program.json`, discovered the
registered operation over MCP, and sent 25 stepwise JSON-RPC requests. The agent
inspected claims before authoring classifications; no Python classifier or mock
response function produced those decisions. No separate inference provider API
was called. `worker-decisions.md` records the reasoning and timing.

The program joins operation results with project, category-owner, and urgency
facts, filtering urgency above 2. Three issues were submitted: a payment outage,
a search indexing incident, and a cosmetic backlog request. After payment input
advanced, an old incident classification completed stale and produced no current
route. The fresh security classification routed the updated issue to the security
owner. Updating search ownership changed only its route.

The root agent independently replayed the raw calls with a Python set/join
oracle. It imports no Lemmalog/DDlog implementation and checks the reviewed task
rule explicitly. Seventeen checks and four route snapshots passed; a separate
negative probe injecting a stale payment route was rejected.

Run the independent check from the repository root:

```sh
python3 scripts/verify-agent-author.py docs/evidence/registered-author
```

Backend executable SHA-256:
`e8dceab1fb34bc7d09a58d86a08639e56f5586abacc643e3cfa6aa81969115ff`.
Backend source: `0317f0a4e5ae3adc05b40b89b3369d22bdd2f1d6`.
The author verified that binary hash before execution; the root independently
verified it against the clean source checkout and retained compiled binary.
The generated source is retained as `program.dl`; compiler and executable hashes
are recorded in `provenance.txt`. One DDlog program compilation succeeded using the existing v1.2.3 toolchain;
the generated program ran on Differential/Timely as described in the parent
backend evidence.

This is actual agent-authored tool use and worker reasoning. It is not
server-enforced constrained decoding, a model-quality benchmark, a successful
external inference API call, or durable external execution. The oracle treats
agent classifications as external input and tests correct routing and lifecycle,
not the general accuracy of those classifications.
