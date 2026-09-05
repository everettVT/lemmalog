"""Integrity tests for the receipt evaluator; no MCP process or compilation."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("dogfood_trace", ROOT / "scripts" / "check_ddlog_dogfood_trace.py")
trace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trace)

RULES = ("eligible(P,R,F) :- finding(P,R,F,S), S =< 2.\n"
         "actionable(P,F) :- eligible(P,R,F), revision(P,R), support(P,R,F,U).")
SCENARIO = json.loads((ROOT / "docs" / "dogfood-scenario.json").read_text())


class ReceiptBuilder:
    def __init__(self):
        self.events = [{"event": "session_start", "actor": "test-author"},
                       {"event": "server_start", "pid": 1}]
        self.sequence = 0

    def call(self, stage, method, params, result):
        self.sequence += 1
        common = {"sequence": self.sequence, "actor": "test-author", "stage": stage,
                  "request": {"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": copy.deepcopy(params)}}
        self.events.append({"event": "request", **copy.deepcopy(common)})
        self.events.append({"event": "exchange", **common, "elapsed_seconds": 0.1,
                            "response": {"jsonrpc": "2.0", "id": self.sequence, "result": copy.deepcopy(result)}})

    def tool(self, stage, name, arguments, payload, failed=False):
        self.call(stage, "tools/call", {"name": name, "arguments": arguments},
                  {"isError": failed, "content": [{"type": "text", "text": payload if failed else json.dumps(payload)}]})

    def finish(self):
        self.events.append({"event": "session_end", "calls": self.sequence,
                            "process_group_gone": True, "cleanup_error": None, "server_exit_code": 0})


def make_complete_trace(close=True):
    """Synthesize valid transport around the independently tested set oracle."""
    builder, facts = ReceiptBuilder(), trace.FactOracle()
    builder.call("initialize", "initialize", {}, {"serverInfo": {"name": "lemmalog-ddlog"}})
    builder.call("discovery", "tools/list", {}, {"tools": [{"name": name} for name in sorted(trace.TOOLS)]})
    threshold, version = 2, 0
    phases = {phase["id"]: phase for phase in SCENARIO["phases"]}
    for stage in trace.STEPS:
        if stage in ("initial_install", "policy_change", "failed_build"):
            if stage == "policy_change":
                threshold = 3
            rules = RULES.replace("=< 2", f"=< {threshold}")
            args = {"rules": rules, "schemas": trace.SCHEMAS}
            if stage == "failed_build":
                builder.tool(stage, "lemmalog_install_rules", args,
                             "DDlog compilation failed; previous version retained. See build.log", True)
            else:
                version += 1
                builder.tool(stage, "lemmalog_install_rules", args,
                             {"version": version, "backend": "ddlog/differential-dataflow",
                              "replayed_facts": sum(map(len, facts.snapshot().values()))})
        else:
            changes = phases[stage]["changes"]
            if stage == "bad_mutation":
                builder.tool(stage, "apply_changes", {"changes": changes},
                             "Expected signed 64-bit integer", True)
            else:
                before = facts.expected(threshold)
                facts.apply(changes)
                after = facts.expected(threshold)
                rows = [f"R_actionable{{.f0 = {p}, .f1 = {f}}}: +1\n" for p, f in sorted(after - before)]
                rows += [f"R_actionable{{.f0 = {p}, .f1 = {f}}}: -1\n" for p, f in sorted(before - after)]
                dump = "R_actionable:\n" + "".join(rows) if rows else ""
                builder.tool(stage, "apply_changes", {"changes": changes}, {"version": version, "deltas": dump})
        if stage != "initial_install":
            dump = "".join(f"R_actionable{{.f0 = {p}, .f1 = {f}}}\n" for p, f in sorted(facts.expected(threshold)))
            builder.tool(stage + "_query", "lemmalog_query", {"predicate": "actionable"},
                         {"version": version, "rows": dump})
        if stage == "failed_build":
            bindings = "".join(f"Evidence0{{.v_F = {f}, .v_P = {p}, .v_R = {r}, .v_S = {s}}}\n"
                               for p, r, f, s in facts.snapshot()["finding"] if s <= threshold)
            builder.tool("failed_build_why", "lemmalog_why", {"rule": 0},
                         {"version": version, "rule": 0, "bindings": bindings, "scope": trace.SCOPE})
    if close:
        builder.finish()
    return builder


def find_exchange(events, stage):
    return next(event for event in events if event.get("event") == "exchange" and event.get("stage") == stage)


def alter_payload(events, stage, **updates):
    exchange = find_exchange(events, stage)
    content = exchange["response"]["result"]["content"][0]
    payload = json.loads(content["text"])
    payload.update(updates)
    content["text"] = json.dumps(payload)


class TraceTests(unittest.TestCase):
    def assert_failure(self, events, message):
        report = trace.evaluate_trace(events, SCENARIO)
        self.assertFalse(report["ok"], report)
        self.assertIn(message, " ".join(report["errors"]))
        return report

    def test_complete_trace_proves_all_phases_and_retained_version(self):
        report = trace.evaluate_trace(make_complete_trace().events, SCENARIO)
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(report["complete_author_task"])
        self.assertFalse(report["cleanup_pending"])
        self.assertEqual(report["final_version"], 2)
        self.assertEqual(report["final_expected_rows"], [(1, 103), (1, 104), (1, 105), (2, 201)])
        self.assertEqual([item["stage"] for item in report["expected_tool_errors"]], ["bad_mutation", "failed_build"])

    def test_open_snapshot_requires_explicit_author_completion(self):
        events = make_complete_trace(close=False).events
        report = self.assert_failure(events, "explicit --author-complete")
        self.assertTrue(report["complete_author_task"])
        report = trace.evaluate_trace(events, SCENARIO, author_complete=True)
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(report["cleanup_pending"])

    def test_empty_truncated_and_unpaired_traces_cannot_pass(self):
        self.assert_failure([], "empty trace")
        events = make_complete_trace().events
        self.assert_failure(events[:2], "no completed MCP exchanges")
        self.assert_failure(events[:3], "unanswered request")
        self.assert_failure(events[:4], "missing required author stages")
        self.assert_failure(events[:2] + events[3:], "response without a recorded request")
        events[3]["request"]["params"] = {"tampered": True}
        self.assert_failure(events, "metadata differs")

    def test_transport_failure_and_mismatched_response_ids_are_explicit(self):
        events = make_complete_trace().events
        events[3]["response"]["id"] = 999
        self.assert_failure(events, "response identity")
        events = make_complete_trace().events
        events[3]["event"] = "transport_failure"
        events[3]["error"] = "deadline exceeded"
        self.assert_failure(events, "transport failure at initialize: deadline exceeded")

    def test_discovery_missing_or_duplicate_tool_is_not_sufficient(self):
        events = make_complete_trace().events
        tools = find_exchange(events, "discovery")["response"]["result"]["tools"]
        tools[-1] = tools[0]
        self.assert_failure(events, "four expected tools")

    def test_tampered_fixture_repeated_phase_and_missing_query_fail(self):
        events = make_complete_trace().events
        for event in events:
            if event.get("stage") == "duplicate":
                event["request"]["params"]["arguments"]["changes"][0]["values"][-1] = 777
        self.assert_failure(events, "differs from frozen fixture")
        events = make_complete_trace().events
        for event in events:
            if event.get("stage") == "alternate_support":
                event["stage"] = "duplicate"
        self.assert_failure(events, "unexpected/repeated mutation stage")
        events = make_complete_trace().events
        # Relabel a query as a valid witness: transport remains intact, but no
        # actionable observation can close the preceding mutation boundary.
        for event in events:
            if event.get("stage") == "duplicate_query":
                event["request"]["params"] = {"name": "lemmalog_why", "arguments": {"rule": 0}}
                if event["event"] == "exchange":
                    event["response"]["result"]["content"][0]["text"] = json.dumps(
                        {"version": 1, "rule": 0, "scope": trace.SCOPE,
                         "bindings": "Evidence0{.v_F = 101, .v_P = 1, .v_R = 1, .v_S = 1}\n"
                                     "Evidence0{.v_F = 201, .v_P = 2, .v_R = 7, .v_S = 2}\n"})
        self.assert_failure(events, "missing actionable query after duplicate")

    def test_exact_rows_deltas_versions_and_replay_counts_are_enforced(self):
        cases = [
            ("seed_query", {"rows": ""}, "rows mismatch"),
            ("withdraw_last_support", {"deltas": ""}, "delta mismatch"),
            ("policy_change", {"replayed_facts": 0}, "replay count mismatch"),
            ("bad_mutation_query", {"version": 3}, "query version mismatch"),
            ("failed_build_query", {"version": 3}, "query version mismatch"),
        ]
        for stage, payload, error in cases:
            with self.subTest(stage=stage):
                events = make_complete_trace().events
                alter_payload(events, stage, **payload)
                self.assert_failure(events, error)

    def test_unexpected_tool_error_and_accepted_bad_mutation_fail(self):
        events = make_complete_trace().events
        result = find_exchange(events, "seed")["response"]["result"]
        result.update(isError=True, content=[{"type": "text", "text": "unplanned build failure"}])
        self.assert_failure(events, "unexpected tool error at seed")
        events = make_complete_trace().events
        result = find_exchange(events, "bad_mutation")["response"]["result"]
        result.update(isError=False, content=[{"type": "text", "text": '{"version":2,"deltas":""}'}])
        self.assert_failure(events, "expected rejection was accepted")

    def test_false_witnesses_and_recursive_scope_claims_fail(self):
        events = make_complete_trace().events
        alter_payload(events, "failed_build_why", bindings="Evidence0{.v_F = 999, .v_P = 1, .v_R = 2, .v_S = 1}\n")
        self.assert_failure(events, "nonfactual or incomplete direct witnesses")
        events = make_complete_trace().events
        alter_payload(events, "failed_build_why", scope="Full recursive provenance")
        self.assert_failure(events, "scope is missing or changed")

    def test_supervisor_probes_are_checked_without_substituting_for_author_steps(self):
        builder = make_complete_trace(close=False)
        builder.tool("supervisor_duplicate", "apply_changes", {"changes": []}, {"version": 2, "deltas": ""})
        builder.tool("supervisor_duplicate_query", "lemmalog_query", {"predicate": "actionable"},
                     {"version": 2, "rows": "".join(f"R_actionable{{.f0 = {p}, .f1 = {f}}}\n"
                                                    for p, f in ((1, 103), (1, 104), (1, 105), (2, 201)))})
        builder.finish()
        report = trace.evaluate_trace(builder.events, SCENARIO)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(len(report["supervisor_exchanges"]), 2)
        events = make_complete_trace().events
        for event in events:
            if event.get("stage") == "failed_build_query":
                event["stage"] = "supervisor_replacement_query"
        self.assert_failure(events, "cannot substitute")

    def test_failed_cleanup_does_not_erase_completed_author_evidence(self):
        events = make_complete_trace().events
        events[-1]["process_group_gone"] = False
        report = self.assert_failure(events, "cleanup was not confirmed")
        self.assertTrue(report["complete_author_task"])


class ProgramAndWitnessTests(unittest.TestCase):
    def test_variable_renaming_body_order_and_rule_order_are_not_exact_text_scoring(self):
        program = ("actionable(Project,Id) :- support(Project,Rev,Id,Source), "
                   "revision(Project,Rev), eligible(Project,Rev,Id).\n"
                   "eligible(Project,Rev,Id) :- Sev =< 3, finding(Project,Rev,Id,Sev).")
        shapes = trace.program_shape(program, 3)
        self.assertEqual(shapes["actionable"]["index"], 0)
        self.assertEqual(shapes["eligible"]["vars"], ("Project", "Rev", "Id", "Sev"))

    def test_bad_composition_hardcoded_ids_and_wrong_policy_fail(self):
        for rules in (RULES.replace("revision(P,R)", "revision(P,F)"),
                      RULES.replace("support(P,R,F,U)", "support(1,R,F,U)"),
                      RULES.replace("=< 2", "=< 3"), RULES.split("\n")[0]):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                trace.program_shape(rules, 2)

    def test_witness_parser_rejects_duplicate_and_noncanonical_bindings(self):
        row = "Evidence1{.v_F = 10, .v_P = 1}\n"
        for text in (row + row, "Evidence1{.v_F = 10, .v_F = 10}\n",
                     "Evidence1{.v_P = 1, .v_F = 10}\n", "Evidence1{.v_F = 01}\n",
                     "Evidence0{.v_F = 10}\n", row + "\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                trace.witness_rows(text, 1)


if __name__ == "__main__":
    unittest.main()
