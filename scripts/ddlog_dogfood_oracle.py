#!/usr/bin/env python3
"""Independent set/join oracle for the reviewer-evidence DDlog dogfood.

No authored rules, DDlog evaluation, or backend implementation is consulted.
Input facts are revision(project, rev), finding(project, rev, id, severity),
and support(project, rev, id, source). All fields are signed 64-bit integers.
Multiple revisions and support sources coexist; inserts never perform upserts.

CLI example:
    python3 scripts/ddlog_dogfood_oracle.py check \
        --facts facts.json --threshold 2 --rows rows.txt
"""

import argparse
import json
import re
import sys
from pathlib import Path


MIN_I64 = -(2**63)
MAX_I64 = 2**63 - 1
ARITIES = {"revision": 2, "finding": 4, "support": 4}
TARGET = "R_actionable"
Row = tuple[int, int]


def _int64(value, label="value"):
    if type(value) is not int or not MIN_I64 <= value <= MAX_I64:
        raise ValueError(f"{label} must be a signed 64-bit integer")
    return value


class FactOracle:
    """Transactional input sets with a rule-independent expected-state query."""

    def __init__(self, facts=None):
        self._facts = {name: set() for name in ARITIES}
        if facts is not None:
            if not isinstance(facts, dict) or any(name not in ARITIES for name in facts):
                raise ValueError("facts must map only revision, finding, and support to rows")
            changes = []
            for name, rows in facts.items():
                if not isinstance(rows, list):
                    raise ValueError(f"facts[{name!r}] must be a list of rows")
                changes.extend(
                    {"op": "insert", "predicate": name, "values": row} for row in rows
                )
            self.apply(changes)

    def apply(self, changes):
        """Apply a JSON-shaped batch atomically; duplicates/absent deletes are no-ops."""
        if not isinstance(changes, list):
            raise ValueError("changes must be a list")
        staged = {name: rows.copy() for name, rows in self._facts.items()}
        for index, change in enumerate(changes):
            if not isinstance(change, dict) or set(change) != {"op", "predicate", "values"}:
                raise ValueError(f"change {index} must contain exactly op, predicate, values")
            op, predicate, values = change["op"], change["predicate"], change["values"]
            if op not in ("insert", "delete"):
                raise ValueError(f"change {index} has unknown operation")
            if not isinstance(predicate, str) or predicate not in ARITIES:
                raise ValueError(f"change {index} has unknown input predicate")
            if not isinstance(values, list) or len(values) != ARITIES[predicate]:
                raise ValueError(f"change {index} has wrong values shape for {predicate}")
            row = tuple(_int64(value, f"change {index} field {field}")
                        for field, value in enumerate(values))
            if op == "insert":
                staged[predicate].add(row)
            else:
                staged[predicate].discard(row)
        self._facts = staged

    def snapshot(self):
        """Return a detached, deterministic JSON-shaped copy of retained facts."""
        return {name: [list(row) for row in sorted(rows)]
                for name, rows in self._facts.items()}

    def expected(self, threshold):
        """Return unique (project, finding_id) rows with a matching current revision."""
        _int64(threshold, "threshold")
        supported = {(project, rev, finding_id)
                     for project, rev, finding_id, _source in self._facts["support"]}
        return {(project, finding_id)
                for project, rev, finding_id, severity in self._facts["finding"]
                if severity <= threshold
                and (project, rev) in self._facts["revision"]
                and (project, rev, finding_id) in supported}


_INTEGER = r"(?:0|-?[1-9][0-9]*)"
_RELATION = r"(?:R_[A-Za-z][A-Za-z0-9_]*|Evidence(?:0|[1-9][0-9]*))"
_STRING = r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"'
_FIELD = re.compile(rf"\.([A-Za-z][A-Za-z0-9_]*) = ({_INTEGER}|{_STRING})")
_RECORD = re.compile(rf"({_RELATION})\{{(.*)\}}")
_DELTA = re.compile(rf"({_RELATION}\{{.*\}}): ([+-][1-9][0-9]*)")
_HEADER = re.compile(rf"({_RELATION}):")


def _lines(text):
    if not isinstance(text, str):
        raise ValueError("DDlog output must be text")
    if text == "":
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    if any(not line or "\r" in line for line in lines):
        raise ValueError("Blank lines and carriage returns are not canonical DDlog output")
    return lines


def _record(text):
    match = _RECORD.fullmatch(text)
    if match is None:
        raise ValueError(f"Malformed DDlog record: {text!r}")
    relation, body = match.groups()
    fields, offset = {}, 0
    while offset < len(body):
        field = _FIELD.match(body, offset)
        if field is None:
            raise ValueError(f"Malformed DDlog fields: {text!r}")
        name, literal = field.groups()
        if name in fields:
            raise ValueError(f"Duplicate DDlog field: {name}")
        fields[name] = json.loads(literal) if literal.startswith('"') else _int64(int(literal))
        offset = field.end()
        if offset < len(body):
            if body[offset:offset + 2] != ", " or offset + 2 == len(body):
                raise ValueError(f"Malformed DDlog field separator: {text!r}")
            offset += 2
    if not fields:
        raise ValueError(f"Empty DDlog record: {text!r}")
    if relation == TARGET:
        if list(fields) != ["f0", "f1"]:
            raise ValueError("R_actionable requires exactly .f0 then .f1")
        return relation, (_int64(fields["f0"]), _int64(fields["f1"]))
    return relation, None


def parse_rows(text) -> set[Row]:
    """Read canonical dump rows; ignore well-formed EvidenceN/intermediate rows."""
    rows = set()
    for line in _lines(text):
        relation, row = _record(line)
        if relation == TARGET:
            if row in rows:
                raise ValueError(f"Duplicate R_actionable row: {row}")
            rows.add(row)
    return rows


def parse_deltas(text) -> dict[Row, int]:
    """Read headed commit dump_changes sections; target weights must be +/-1.

    Repeated target rows (including cancelling pairs) are rejected, not summed.
    Evidence and intermediate relation sections do not affect the target delta.
    """
    changes, seen_sections = {}, set()
    section, section_rows = None, 0
    for line in _lines(text):
        header = _HEADER.fullmatch(line)
        if header:
            if section is not None and section_rows == 0:
                raise ValueError(f"Empty DDlog delta section: {section}")
            section = header.group(1)
            if section in seen_sections:
                raise ValueError(f"Repeated DDlog delta section: {section}")
            seen_sections.add(section)
            section_rows = 0
            continue
        delta = _DELTA.fullmatch(line)
        if delta is None:
            raise ValueError(f"Malformed DDlog delta: {line!r}")
        relation, row = _record(delta.group(1))
        if section != relation:
            raise ValueError(f"DDlog delta row does not match its section: {line!r}")
        section_rows += 1
        if relation == TARGET:
            weight = int(delta.group(2))
            if weight not in (-1, 1):
                raise ValueError("R_actionable delta weight must be +1 or -1")
            if row in changes:
                raise ValueError(f"Duplicate R_actionable delta: {row}")
            changes[row] = weight
    if section is not None and section_rows == 0:
        raise ValueError(f"Empty DDlog delta section: {section}")
    return changes


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_facts(path):
    return FactOracle(json.loads(path.read_text(), object_pairs_hook=_json_object))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Compare captured rows and optional deltas to input facts")
    check.add_argument("--facts", type=Path, required=True,
                       help="JSON object mapping revision/finding/support to arrays of integer rows")
    check.add_argument("--threshold", type=int, required=True)
    check.add_argument("--rows", type=Path, required=True, help="File containing raw DDlog dump rows")
    check.add_argument("--previous-facts", type=Path)
    check.add_argument("--deltas", type=Path, help="Raw commit dump_changes; requires --previous-facts")
    args = parser.parse_args(argv)
    if bool(args.deltas) != bool(args.previous_facts):
        parser.error("--deltas and --previous-facts must be supplied together")
    try:
        expected = _read_facts(args.facts).expected(args.threshold)
        observed = parse_rows(args.rows.read_text())
        result = {"ok": expected == observed, "expected_rows": sorted(expected),
                  "observed_rows": sorted(observed)}
        if args.deltas:
            previous = _read_facts(args.previous_facts).expected(args.threshold)
            expected_delta = {row: 1 for row in expected - previous}
            expected_delta.update({row: -1 for row in previous - expected})
            observed_delta = parse_deltas(args.deltas.read_text())
            result["ok"] = result["ok"] and expected_delta == observed_delta
            result["expected_deltas"] = sorted((*row, weight) for row, weight in expected_delta.items())
            result["observed_deltas"] = sorted((*row, weight) for row, weight in observed_delta.items())
        print(json.dumps(result, sort_keys=True))
        return 0 if result["ok"] else 1
    except (OSError, ValueError) as error:
        print(f"oracle input error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
