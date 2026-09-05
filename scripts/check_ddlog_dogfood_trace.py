#!/usr/bin/env python3
"""Check a recorded MCP dogfood session against its frozen, independent oracle.

This reads receipts only: it does not call MCP, evaluate authored rules, or build.
--author-complete explicitly permits an open session snapshot for supervisor work;
cleanup remains pending until a later trace contains session_end.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

from ddlog_dogfood_oracle import FactOracle, MAX_I64, MIN_I64, parse_deltas, parse_rows


TOOLS = {"lemmalog_install_rules", "apply_changes", "lemmalog_query", "lemmalog_why"}
SCHEMAS = {name: {"input": input_, "fields": ["int"] * size}
           for name, input_, size in (("revision", True, 2), ("finding", True, 4),
                                     ("support", True, 4), ("eligible", False, 3),
                                     ("actionable", False, 2))}
PHASE_IDS = ["seed", "duplicate", "alternate_support", "withdraw_last_support",
             "restore_support", "revision_change", "bad_mutation", "corrected_mutation"]
STEPS = ["initial_install", *PHASE_IDS[:6], "policy_change", *PHASE_IDS[6:], "failed_build"]
SCOPE = "Direct rule variable bindings; not recursive proof trees or confidence provenance"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(text):
    return json.loads(text, object_pairs_hook=strict_object)


def exchanges_from_events(events):
    """Validate transport pairing before interpreting any tool-level evidence."""
    require(isinstance(events, list) and events, "empty trace")
    require(events[0].get("event") == "session_start", "missing initial session_start")
    exchanges, pending, end = [], None, None
    servers, next_sequence = 0, 1
    for index, event in enumerate(events[1:], 1):
        require(isinstance(event, dict), f"event {index} is not an object")
        kind = event.get("event")
        require(end is None, "events appear after session_end")
        if kind == "server_start":
            servers += 1
            require(servers == 1 and next_sequence == 1 and pending is None,
                    "misplaced or duplicate server_start")
        elif kind == "request":
            require(servers == 1 and pending is None, "overlapping request or missing server_start")
            require(type(event.get("sequence")) is int and event["sequence"] == next_sequence,
                    "request sequences must be contiguous from 1")
            request = event.get("request")
            require(isinstance(request, dict) and request.get("jsonrpc") == "2.0"
                    and type(request.get("id")) is int and request["id"] == next_sequence,
                    "invalid JSON-RPC request identity")
            require(isinstance(request.get("method"), str)
                    and isinstance(request.get("params"), dict), "invalid request method/params")
            require(isinstance(event.get("stage"), str) and event["stage"]
                    and isinstance(event.get("actor"), str) and event["actor"],
                    "missing request stage or actor")
            pending = event
        elif kind in ("exchange", "transport_failure"):
            require(pending is not None, "response without a recorded request")
            require(all(event.get(key) == pending.get(key)
                        for key in ("sequence", "actor", "stage", "request")),
                    "exchange metadata differs from its recorded request")
            elapsed = event.get("elapsed_seconds")
            require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0,
                    "invalid exchange elapsed_seconds")
            require(kind != "transport_failure",
                    f"transport failure at {event.get('stage')}: {event.get('error')}")
            response = event.get("response")
            require(isinstance(response, dict) and response.get("jsonrpc") == "2.0"
                    and type(response.get("id")) is int and response["id"] == next_sequence
                    and (("result" in response) != ("error" in response)),
                    "invalid JSON-RPC response identity/result")
            exchanges.append(event)
            pending = None
            next_sequence += 1
        elif kind == "session_end":
            require(pending is None, "session ended with an unanswered request")
            require(type(event.get("calls")) is int and event["calls"] == len(exchanges),
                    "session_end call count differs from exchanges")
            end = event
        else:
            raise ValueError(f"unknown or misplaced event kind: {kind!r}")
    require(pending is None, "trace ends with an unanswered request")
    require(servers == 1 and exchanges, "trace has no completed MCP exchanges")
    return exchanges, end


def tool_result(response):
    require("error" not in response, f"unexpected JSON-RPC error: {response.get('error')}")
    result = response["result"]
    require(isinstance(result, dict) and type(result.get("isError")) is bool,
            "malformed MCP tool result")
    content = result.get("content")
    require(isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict)
            and content[0].get("type") == "text" and isinstance(content[0].get("text"), str),
            "expected exactly one text content block")
    if result["isError"]:
        return True, content[0]["text"]
    payload = read_json(content[0]["text"])
    require(isinstance(payload, dict), "successful tool payload is not an object")
    return False, payload


def program_shape(rules, threshold):
    """Check two-rule composition up to variable renaming and body ordering.

    This checks the requested authoring form, not output truth. FactOracle owns
    output expectations independently. Returned variable names label direct
    factual witnesses without interpreting arbitrary authored logic.
    """
    require(isinstance(rules, str), "program rules must be text")
    clauses = [part.strip() for part in rules.split(".") if part.strip()]
    require(len(clauses) == 2 and rules.rstrip().endswith("."), "expected two composed rules")
    atoms = re.compile(r"([a-z][A-Za-z0-9_]*)\(\s*([A-Za-z0-9_,\s]+)\s*\)")
    shapes = {}
    for index, clause in enumerate(clauses):
        require(clause.count(":-") == 1, "expected rule head and positive body")
        head, body = (part.strip() for part in clause.split(":-"))
        head_match = atoms.fullmatch(head)
        require(head_match is not None, "malformed composed rule head")
        name = head_match.group(1)
        require(name in ("eligible", "actionable") and name not in shapes,
                "expected one eligible and one actionable rule")
        head_args = tuple(x.strip() for x in head_match.group(2).split(","))
        body_atoms = {}
        for match in atoms.finditer(body):
            predicate = match.group(1)
            require(predicate not in body_atoms, "repeated atom in composed rule")
            body_atoms[predicate] = tuple(x.strip() for x in match.group(2).split(","))
        for args in (head_args, *body_atoms.values()):
            require(all(re.fullmatch(r"[A-Z][A-Za-z0-9_]*", arg) for arg in args),
                    "rule atoms must bind variables, without hardcoded IDs")
        residual = atoms.sub("", body).strip().strip(",").strip()
        if name == "eligible":
            require(set(body_atoms) == {"finding"} and len(body_atoms["finding"]) == 4,
                    "eligible must derive from finding")
            project, rev, finding, severity = body_atoms["finding"]
            require(len(set((project, rev, finding, severity))) == 4,
                    "eligible unexpectedly aliases finding fields")
            require(head_args == (project, rev, finding), "eligible projects the wrong fields")
            normalized = re.sub(r"\s+", "", residual)
            require(normalized in (f"{severity}=<{threshold}", f"{severity}<={threshold}"),
                    "eligible threshold comparison differs from the requested policy")
            shapes[name] = {"index": index, "vars": (project, rev, finding, severity)}
        else:
            require(set(body_atoms) == {"eligible", "revision", "support"}
                    and len(body_atoms["eligible"]) == 3 and not residual.replace(",", "").strip(),
                    "actionable must compose eligible, revision, and support")
            project, rev, finding = body_atoms["eligible"]
            require(len(set((project, rev, finding))) == 3
                    and head_args == (project, finding)
                    and body_atoms["revision"] == (project, rev)
                    and len(body_atoms["support"]) == 4
                    and body_atoms["support"][:3] == (project, rev, finding),
                    "actionable has incorrect join keys or projection")
            source = body_atoms["support"][3]
            require(source not in (project, rev, finding), "support source unexpectedly aliases a join key")
            shapes[name] = {"index": index, "vars": (project, rev, finding, source)}
    return shapes


def witness_rows(text, index):
    require(isinstance(text, str), "witness bindings must be text")
    if not text:
        return set()
    rows = set()
    for line in text.removesuffix("\n").split("\n"):
        match = re.fullmatch(rf"Evidence{index}\{{(.+)\}}", line)
        require(match is not None, "malformed or mismatched direct witness record")
        fields = {}
        for item in match.group(1).split(", "):
            field = re.fullmatch(r"\.v_([A-Z][A-Za-z0-9_]*) = (0|-?[1-9][0-9]*)", item)
            require(field is not None, "malformed direct witness field")
            key, number = field.groups()
            require(key not in fields, "duplicate direct witness field")
            value = int(number)
            require(MIN_I64 <= value <= MAX_I64, "direct witness is outside int64")
            fields[key] = value
        require(list(fields) == sorted(fields), "noncanonical witness field order")
        row = tuple(fields.items())
        require(row not in rows, "duplicate direct witness row")
        rows.add(row)
    return rows


def expected_witnesses(facts, shape, threshold, relation):
    snapshot = facts.snapshot()
    if relation == "eligible":
        tuples = {tuple(row) for row in snapshot["finding"] if row[3] <= threshold}
    else:
        eligible = {tuple(row[:3]) for row in snapshot["finding"] if row[3] <= threshold}
        revisions = {tuple(row) for row in snapshot["revision"]}
        tuples = {tuple(row) for row in snapshot["support"]
                  if tuple(row[:3]) in eligible and tuple(row[:2]) in revisions}
    return {tuple(sorted(zip(shape["vars"], row))) for row in tuples}


def evaluate_trace(events, scenario, author_complete=False):
    report = {"ok": False, "complete_author_task": False, "cleanup_pending": True,
              "errors": [], "checks": [], "expected_tool_errors": [],
              "supervisor_exchanges": [], "witness_scope": SCOPE,
              "limitations": ["Actor labels alone do not establish model authorship.",
                              "A failed_build label and tool error do not independently prove the operator flag injection.",
                              "Direct witnesses are factual variable bindings, not recursive provenance."]}
    try:
        exchanges, end = exchanges_from_events(events)
        report["exchange_count"] = len(exchanges)
        report["cleanup_pending"] = end is None
        require(isinstance(scenario, dict) and scenario.get("initial_threshold") == 2
                and scenario.get("revised_threshold") == 3, "unexpected fixture policy thresholds")
        phases = scenario.get("phases")
        require(isinstance(phases, list) and [p.get("id") for p in phases] == PHASE_IDS,
                "fixture phases are missing, duplicated, or reordered")
        fixture = {phase["id"]: phase for phase in phases}
        require(fixture["bad_mutation"].get("expected_error") is True, "fixture lacks typed failure")
        facts, threshold, version = FactOracle(), 2, 0
        initialized, discovered, shapes = False, False, None
        step_index, pending_query, pending_witness = 0, None, False
        author_actor = events[0].get("actor")
        report["actor_label"] = author_actor
        for exchange in exchanges:
            stage, request = exchange["stage"], exchange["request"]
            sequence, response = exchange["sequence"], exchange["response"]
            method, params = request["method"], request["params"]
            supervisor = stage.startswith("supervisor_")
            if supervisor:
                require(step_index == len(STEPS), "supervisor checks precede required author stages")
                if not report["complete_author_task"]:
                    require(pending_query is None and not pending_witness,
                            "supervisor checks cannot substitute for required author observations")
                report["complete_author_task"] = True
                report["supervisor_exchanges"].append({"sequence": sequence, "stage": stage})
            else:
                require(exchange["actor"] == author_actor, "author actor changed without a supervisor label")
            require("error" not in response, f"unexpected JSON-RPC error at {stage}: {response.get('error')}")
            if method == "initialize":
                require(not initialized and not discovered and version == 0, "duplicate or misplaced initialize")
                require(isinstance(response["result"], dict)
                        and response["result"].get("serverInfo", {}).get("name") == "lemmalog-ddlog",
                        "initialize did not identify the expected MCP server")
                initialized = True
                continue
            if method == "tools/list":
                require(initialized and not discovered and version == 0, "duplicate or misplaced discovery")
                listed = response["result"].get("tools", [])
                require(isinstance(listed, list) and len(listed) == 4
                        and {item.get("name") for item in listed} == TOOLS,
                        "discovery must expose exactly the four expected tools")
                discovered = True
                continue
            require(method == "tools/call" and discovered, f"unsupported method or call before discovery: {method}")
            name, args = params.get("name"), params.get("arguments")
            require(name in TOOLS and isinstance(args, dict), "unknown tool or malformed arguments")
            failed, payload = tool_result(response)
            mutation = name in ("lemmalog_install_rules", "apply_changes")
            if mutation:
                require(pending_query is None, f"missing actionable query after {pending_query}")
                require(not pending_witness, "missing direct witness check after failed_build")
                if not supervisor:
                    require(step_index < len(STEPS) and stage == STEPS[step_index],
                            f"unexpected/repeated mutation stage {stage}; expected "
                            f"{STEPS[step_index] if step_index < len(STEPS) else 'no more author mutations'}")
                    step_index += 1
            expected_error = stage in ("bad_mutation", "failed_build") and mutation and not supervisor
            require(failed == expected_error,
                    f"{'unexpected tool error' if failed else 'expected rejection was accepted'} at {stage}: {payload}")
            if name == "lemmalog_install_rules":
                require(not supervisor and stage in ("initial_install", "policy_change", "failed_build"),
                        "install occurred outside an author installation stage")
                require(args.get("schemas") == SCHEMAS and set(args) == {"rules", "schemas"},
                        "installed schemas differ from the fixed task contracts")
                require(all(type(schema.get("input")) is bool for schema in args["schemas"].values()),
                        "schema input flags must be booleans")
                next_threshold = 3 if stage == "policy_change" else threshold
                next_shapes = program_shape(args.get("rules"), next_threshold)
                if failed:
                    require("DDlog compilation failed" in payload and "previous version retained" in payload,
                            "failed_build did not report compilation failure with previous version retained")
                    report["expected_tool_errors"].append({"stage": stage, "sequence": sequence, "message": payload})
                    pending_witness = True
                else:
                    require(payload.get("backend") == "ddlog/differential-dataflow", "install backend mismatch")
                    require(type(payload.get("version")) is int and payload["version"] == version + 1,
                            "successful install version did not advance exactly once")
                    count = sum(len(rows) for rows in facts.snapshot().values())
                    require(type(payload.get("replayed_facts")) is int and payload["replayed_facts"] == count,
                            "retained fact replay count mismatch")
                    threshold, version, shapes = next_threshold, version + 1, next_shapes
                    report["checks"].append({"kind": "install", "stage": stage, "sequence": sequence,
                                             "version": version, "replayed_facts": count, "threshold": threshold})
                if stage != "initial_install":
                    pending_query = stage
            elif name == "apply_changes":
                require(version > 0 and set(args) == {"changes"}, "invalid mutation arguments or no installed program")
                if not supervisor:
                    require(stage in fixture and args["changes"] == fixture[stage]["changes"],
                            f"mutation differs from frozen fixture at {stage}")
                before = facts.expected(threshold)
                if failed:
                    old_snapshot = facts.snapshot()
                    try:
                        facts.apply(args["changes"])
                    except ValueError:
                        pass
                    else:
                        raise ValueError("bad_mutation fixture was valid in the independent oracle")
                    require(facts.snapshot() == old_snapshot and "signed 64-bit integer" in payload,
                            "typed mutation failure was not the expected atomic rejection")
                    report["expected_tool_errors"].append({"stage": stage, "sequence": sequence, "message": payload})
                else:
                    facts.apply(args["changes"])
                    after = facts.expected(threshold)
                    expected = {row: 1 for row in after - before}
                    expected.update({row: -1 for row in before - after})
                    observed = parse_deltas(payload.get("deltas"))
                    require(type(payload.get("version")) is int and payload["version"] == version,
                            f"mutation version mismatch at {stage}")
                    report["checks"].append({"kind": "deltas", "stage": stage, "sequence": sequence,
                                             "supervisor": supervisor, "expected": sorted((*r, w) for r, w in expected.items()),
                                             "observed": sorted((*r, w) for r, w in observed.items())})
                    require(observed == expected, f"actionable delta mismatch at {stage}")
                pending_query = stage
            elif name == "lemmalog_query":
                require(version > 0 and args == {"predicate": "actionable"},
                        "only actionable queries are scored by this fixture evaluator")
                require(type(payload.get("version")) is int and payload["version"] == version,
                        f"query version mismatch at {stage}")
                observed, expected = parse_rows(payload.get("rows")), facts.expected(threshold)
                report["checks"].append({"kind": "rows", "stage": stage, "sequence": sequence,
                                         "after": pending_query, "supervisor": supervisor,
                                         "expected": sorted(expected), "observed": sorted(observed), "version": version})
                require(observed == expected, f"actionable rows mismatch at {stage}")
                pending_query = None
            else:
                require(version > 0 and set(args) == {"rule"} and type(args["rule"]) is int,
                        "invalid direct witness query")
                require(type(payload.get("version")) is int and payload["version"] == version
                        and type(payload.get("rule")) is int and payload["rule"] == args["rule"],
                        "direct witness version/rule mismatch")
                require(payload.get("scope") == SCOPE, "direct witness scope is missing or changed")
                relation = next((name for name, shape in shapes.items() if shape["index"] == args["rule"]), None)
                require(relation is not None, "unknown direct witness rule index")
                observed = witness_rows(payload.get("bindings"), args["rule"])
                expected = expected_witnesses(facts, shapes[relation], threshold, relation)
                require(observed == expected, f"nonfactual or incomplete direct witnesses at {stage}")
                report["checks"].append({"kind": "direct_witnesses", "stage": stage, "sequence": sequence,
                                         "rule_relation": relation, "binding_count": len(observed), "version": version})
                pending_witness = False
        require(step_index == len(STEPS), f"missing required author stages: {STEPS[step_index:]}")
        require(pending_query is None, f"missing actionable query after {pending_query}")
        require(not pending_witness, "missing direct witness check after failed_build")
        require(any(check["kind"] == "direct_witnesses" for check in report["checks"]), "no direct witnesses checked")
        report["complete_author_task"] = True
        report["final_version"], report["final_threshold"] = version, threshold
        report["final_expected_rows"] = sorted(facts.expected(threshold))
        report["retained_fact_count"] = sum(len(rows) for rows in facts.snapshot().values())
        if end is None:
            require(author_complete, "session is still open; explicit --author-complete is required for snapshot evaluation")
        else:
            report["cleanup"] = end
            require(end.get("process_group_gone") is True and end.get("cleanup_error") is None
                    and type(end.get("server_exit_code")) is int and end["server_exit_code"] == 0,
                    "session cleanup was not confirmed successful")
        report["ok"] = True
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        report["errors"].append(str(error))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--author-complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        events_bytes, scenario_bytes = args.events.read_bytes(), args.scenario.read_bytes()
        events = [read_json(line) for line in events_bytes.decode().splitlines()]
        report = evaluate_trace(events, read_json(scenario_bytes.decode()), args.author_complete)
        report["inputs"] = {"events_path": str(args.events.resolve()),
                            "events_sha256": hashlib.sha256(events_bytes).hexdigest(),
                            "scenario_path": str(args.scenario.resolve()),
                            "scenario_sha256": hashlib.sha256(scenario_bytes).hexdigest()}
    except (OSError, ValueError) as error:
        report = {"ok": False, "complete_author_task": False, "errors": [str(error)]}
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
