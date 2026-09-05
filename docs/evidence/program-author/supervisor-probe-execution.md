# Delegated supervisor-probe execution

This was a separate execution task after the authoring trial finished. The supervisor reported that its attempt to access exec session SESSION_HANDLE returned `Unknown process id`, so it delegated execution back to the agent that owned the still-open session. Session SESSION_HANDLE remained accessible to this agent; no server restart, rule installation, or fact reload occurred.

The supervisor authored the held-out transactions in `${RUNTIME_DIR}/supervisor-probes.json`. I copied those supplied changes into one transaction per phase and inspected each actual transaction reply followed by an actionable query with the same supervisor stage. I did not author additional rules, alter the fixture file, consult the oracle, or change the original author report. Its 30-request authoring count remains scoped to sequences 1–30. Although the relay's actor label is unchanged, sequences 31–36 are explicitly supervisor-authored probe execution, not additional agent-authored task coverage.

## Actual MCP calls and observations

Exactly six additional MCP tool calls were completed, sequences 31–36:

| Stage | Calls | Observed actionable rows, all version 2 |
|---|---|---|
| supervisor_join_probe | 31 apply_changes; 32 lemmalog_query | (1,103), (1,104), (1,105), (2,201), (91,901), (91,904) |
| supervisor_revision_probe | 33 apply_changes; 34 lemmalog_query | (1,103), (1,104), (1,105), (2,201), (91,904), (92,901), (92,903) |
| supervisor_cleanup_probe | 35 apply_changes; 36 lemmalog_query | (1,103), (1,104), (1,105), (2,201) |

The first transaction's delta contained two distinct Evidence1 bindings for project 91, revision 8, finding 901 (sources 7001 and 7008), but a single actionable addition and one queried row. It also showed negative severity -4 eligible, severity 3 eligible, severity 4 excluded, and mismatched project/revision support not producing extra actionable rows. The second transaction retracted both source witnesses and the single (91,901) row when revision (91,8) was deleted, and added (92,901)/(92,903) after matching support arrived. The final transaction restored the baseline actionable result.

## Transport friction and recovery

The first attempt to send the compact cleanup JSON stopped echoing inside its final value. The session event log still ended at response 34; no request 35 had been received. This was consistent with a PTY canonical input-line limit around 1024 bytes; the cleanup fixture contains 15 deletions, making it longer than the previous request.

I cleared only the pending unsubmitted terminal line with Ctrl-U, then resent the identical compact JSON in two buffered segments. A Ctrl-D after the nonempty first segment flushed terminal input to the existing Python reader; the second segment supplied the rest and the one terminating newline. The relay then received the complete JSON as exactly one request 35, with all 15 supplied deletions. No transaction was split across MCP calls and no mutation was retried after reaching the server. This is supervisor-execution transport friction, separate from the completed authoring trial.

## Termination

After inspecting response 36, I sent `{"stop":true}` as requested. The exec tool returned exit code 0. The final receipt reports:

```json
{
  "event": "session_end",
  "calls": 36,
  "graceful": true,
  "server_exit_code": 0,
  "process_group_gone": true,
  "cleanup_error": null,
  "cleanup_observation_errors": [],
  "cleanup_signal_errors": []
}
```

Receipt path: `${RUNTIME_DIR}/baseline-session/events.jsonl`. No paid/external inference calls or oracle access occurred.
