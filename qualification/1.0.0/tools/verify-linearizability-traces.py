#!/usr/bin/env python3
"""Validate supplied Cerberus serial witnesses independently, without searching.

This standard-library-only tool reads bounded JSONL (or gzip JSONL), checks every
recorded successful witness against real-time intervals and a simple byte-map
specification, and checks stored quiescent snapshots/events. It does not run the
engine, find a witness, prove that no witness exists, authenticate the recorder,
or recheck historical query responses that were not stored in the trace.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

MAX_LINE_BYTES = 2 * 1024 * 1024
MAX_OPERATIONS = 64
MAX_STEPS = 64
MAX_RECORDS = 100_000
MAX_INPUT_CHARGE = 8 * 1024 * 1024
MAX_MODEL_CHARGE = 256 * 1024
MAX_MODEL_ROWS = 1024
U64_MAX = (1 << 64) - 1
DEFINITE_ABORTS = {
    "ABA conflict", "Conflict", "KeyBusy", "Backpressure", "TransactionExpired",
    "transaction validation conflict; no changes committed",
    "commit queue full; no changes committed", "transaction lease expired",
    "declared or written key reserved by another transaction",
}


class InvalidWitness(ValueError):
    """The supplied record is invalid or its claimed witness does not validate."""


def require(condition, message):
    if not condition:
        raise InvalidWitness(message)


def uint(value, label, maximum=U64_MAX):
    require(type(value) is int and 0 <= value <= maximum, f"{label}: unsigned integer required")
    return value


def obj(value, label):
    require(type(value) is dict, f"{label}: object required")
    return value


def array(value, label, maximum=None):
    require(type(value) is list, f"{label}: array required")
    if maximum is not None:
        require(len(value) <= maximum, f"{label}: count exceeds {maximum}")
    return value


def text(value, label):
    require(type(value) is str and value != "", f"{label}: nonempty string required")
    return value


def byte_string(value, label):
    array(value, label)
    require(all(type(item) is int and 0 <= item <= 255 for item in value),
            f"{label}: byte array required")
    return bytes(value)


def rows(value, label, ordered=True):
    answer = []
    for index, row in enumerate(array(value, label)):
        require(type(row) is list and len(row) == 2, f"{label}[{index}]: key/value pair required")
        answer.append((byte_string(row[0], f"{label}[{index}].key"),
                       byte_string(row[1], f"{label}[{index}].value")))
    require(not ordered or all(a[0] < b[0] for a, b in zip(answer, answer[1:])),
            f"{label}: rows must have strict byte-key order without duplicates")
    return answer


def charge(entries):
    return sum(32 + len(key) + len(value) for key, value in entries)


def bound(value, label):
    value = obj(value, label)
    kind = value.get("kind")
    require(kind in ("unbounded", "included", "excluded"), f"{label}: unknown bound")
    if kind == "unbounded":
        require(set(value) == {"kind"}, f"{label}: unbounded bound has extra data")
        return kind, None
    require(set(value) == {"kind", "key"}, f"{label}: bounded key required")
    return kind, byte_string(value["key"], f"{label}.key")


def in_range(key, start, end):
    lower, lower_key = start
    upper, upper_key = end
    return ((lower == "unbounded" or (key >= lower_key if lower == "included" else key > lower_key))
            and (upper == "unbounded" or (key <= upper_key if upper == "included" else key < upper_key)))


def step(value, label):
    value = obj(value, label)
    kind = value.get("step")
    if kind in ("point", "expect", "put"):
        require(set(value) == {"step", "key", "value"}, f"{label}: malformed {kind}")
        key = byte_string(value["key"], f"{label}.key")
        observed = value["value"]
        if observed is None:
            require(kind != "put", f"{label}: put cannot have a null value")
        else:
            observed = byte_string(observed, f"{label}.value")
        return (kind, key, observed), len(key) + (len(observed) if observed is not None else 0)
    if kind == "delete":
        require(set(value) == {"step", "key"}, f"{label}: malformed delete")
        key = byte_string(value["key"], f"{label}.key")
        return (kind, key), len(key)
    if kind == "range":
        require(set(value) == {"step", "start", "end", "rows"}, f"{label}: malformed range")
        start = bound(value["start"], f"{label}.start")
        end = bound(value["end"], f"{label}.end")
        observed = rows(value["rows"], f"{label}.rows", ordered=False)
        return ((kind, start, end, observed), charge(observed)
                + len(start[1] or b"") + len(end[1] or b""))
    raise InvalidWitness(f"{label}: unknown step {kind!r}")


def operation(value, label):
    value = obj(value, label)
    identity = uint(value.get("id"), f"{label}.id")
    uint(value.get("client"), f"{label}.client", (1 << 32) - 1)
    invocation = uint(value.get("invocation"), f"{label}.invocation")
    response = uint(value.get("response"), f"{label}.response")
    require(invocation < response, f"{label}: invalid interval")
    steps = []
    logical_charge = 64
    for index, value_step in enumerate(array(value.get("steps"), f"{label}.steps", MAX_STEPS)):
        normalized, step_charge = step(value_step, f"{label}.steps[{index}]")
        steps.append(normalized)
        logical_charge += 32 + step_charge
    outcome = obj(value.get("outcome"), f"{label}.outcome")
    kind = outcome.get("outcome")
    wrote = None
    position = None
    if kind == "committed":
        require(set(outcome) <= {"outcome", "position", "wrote"}, f"{label}: unknown receipt field")
        position = uint(outcome.get("position"), f"{label}.position")
        wrote = outcome.get("wrote")
        require(wrote is None or type(wrote) is bool, f"{label}: wrote must be boolean when present")
    elif kind == "aborted":
        require(set(outcome) == {"outcome", "reason"}, f"{label}: malformed abort")
        reason = text(outcome.get("reason"), f"{label}.reason")
        require(reason in DEFINITE_ABORTS, f"{label}: unsupported or uncertain abort reason {reason!r}")
        logical_charge += len(reason.encode("utf-8"))
    elif kind == "indeterminate":
        raise InvalidWitness(f"{label}: indeterminate outcomes cannot validate a successful witness")
    else:
        raise InvalidWitness(f"{label}: unknown outcome {kind!r}")
    return {"id": identity, "invocation": invocation, "response": response, "steps": steps,
            "outcome": kind, "position": position, "wrote": wrote}, logical_charge


def validate_record(record):
    """Check only the supplied successful witness; never search for another."""
    record = obj(record, "record")
    require(type(record.get("schema")) is int and record["schema"] == 1, "unsupported record schema")
    version = text(record.get("engine_version"), "engine_version")
    require(re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?", version) is not None,
            "engine_version: semantic version required")
    source = text(record.get("source_sha"), "source_sha")
    require(re.fullmatch(r"[0-9a-f]{40}", source) is not None, "source_sha: exact Git SHA required")
    spec = obj(obj(record.get("workload"), "workload").get("spec"), "workload.spec")
    seed = uint(spec.get("seed"), "seed")
    configuration = (uint(spec.get("operations"), "configured operations", 24),
                     uint(spec.get("threads"), "configured threads", 4))
    require(configuration[0] >= 4 and configuration[1] >= 1
            and configuration[0] % configuration[1] == 0, "invalid generated-workload configuration")
    require(record.get("failure") is None and record.get("failed_audit") is None,
            "record contains a recorded failure")
    linear = obj(record.get("linearizability"), "linearizability")
    require(linear.get("status") == "linearizable", "record does not supply a successful witness")
    uint(linear.get("explored"), "checker explored states")
    initial = obj(record.get("initial"), "initial")
    head = uint(initial.get("position"), "initial.position")
    initial_rows = rows(initial.get("rows"), "initial.rows")
    require(head != 0 or not initial_rows, "position zero must have an empty initial state")
    require(len(initial_rows) <= MAX_MODEL_ROWS and charge(initial_rows) <= MAX_MODEL_CHARGE,
            "initial model exceeds the supported row/byte budget")
    model = dict(initial_rows)
    initial_position = head
    snapshots = {head: dict(model)}
    model_events = []
    logical_charge = charge(initial_rows)
    operations = []
    for index, item in enumerate(array(record.get("operations"), "operations", MAX_OPERATIONS)):
        normalized, item_charge = operation(item, f"operations[{index}]")
        operations.append(normalized)
        logical_charge += item_charge
    require(operations, "empty trace cannot qualify a generated history")
    require(logical_charge <= MAX_INPUT_CHARGE, "history exceeds the logical input-byte budget")
    by_id = {op["id"]: op for op in operations}
    require(len(by_id) == len(operations), "duplicate operation IDs")
    witness = [uint(identity, "witness operation ID")
               for identity in array(linear.get("witness"), "witness", MAX_OPERATIONS)]
    require(len(witness) == len(operations) and len(set(witness)) == len(witness)
            and set(witness) == set(by_id), "witness must contain exactly every operation ID once")
    rank = {identity: index for index, identity in enumerate(witness)}
    for earlier in operations:
        for later in operations:
            require(not (earlier["response"] < later["invocation"]
                         and rank[earlier["id"]] >= rank[later["id"]]),
                    f"witness violates real-time ordering: {earlier['id']} before {later['id']}")
    committed = aborted = writes = flags = 0
    for identity in witness:
        op = by_id[identity]
        if op["outcome"] == "aborted":
            aborted += 1
            continue  # Reads from definite noncommits are provisional.
        committed += 1
        mutations = [item for item in op["steps"] if item[0] in ("put", "delete")]
        mutating = bool(mutations)
        if op["wrote"] is not None:
            require(op["wrote"] == mutating, f"operation {identity}: incorrect wrote receipt flag")
            flags += 1
        expected = head + int(mutating)
        require(expected <= U64_MAX and op["position"] == expected,
                f"operation {identity}: incorrect receipt position")
        staged = dict(model)
        for item in op["steps"]:
            kind = item[0]
            if kind in ("point", "expect"):
                require(staged.get(item[1]) == item[2],
                        f"operation {identity}: {kind} observation disagrees with the serial model")
            elif kind == "range":
                expected_rows = [(key, value) for key, value in sorted(staged.items())
                                 if in_range(key, item[1], item[2])]
                require(expected_rows == item[3],
                        f"operation {identity}: range observation disagrees with the serial model")
            elif kind == "put":
                staged[item[1]] = item[2]
            else:
                staged.pop(item[1], None)
            require(len(staged) <= MAX_MODEL_ROWS and charge(staged.items()) <= MAX_MODEL_CHARGE,
                    f"operation {identity}: reference-model budget exceeded")
        model = staged
        head = expected
        if mutating:
            writes += 1
            snapshots[head] = dict(model)
            model_events.append((head, mutations))
    visible_checks = 0
    for index, visible in enumerate(array(record.get("visible", []), "visible", 64)):
        visible = obj(visible, f"visible[{index}]")
        invocation = uint(visible.get("invocation"), "visible.invocation")
        response = uint(visible.get("response"), "visible.response")
        require(invocation < response, "visible: invalid interval")
        mutators = [op for op in operations if op["outcome"] == "committed"
                    and any(item[0] in ("put", "delete") for item in op["steps"])]
        require(not any(op["invocation"] < response and invocation < op["response"]
                        for op in mutators), "visible: expected a quiescent head audit")
        prefix = max((op["position"] for op in mutators if op["response"] < invocation),
                     default=initial_position)
        require(uint(visible.get("expected_head"), "visible.expected_head") == prefix
                and uint(visible.get("position"), "visible.position") == prefix,
                "visible: incorrect quiescent head position")
        require(rows(visible.get("rows"), "visible.rows") == sorted(snapshots[prefix].items()),
                "visible: snapshot rows disagree with the independent prefix model")
        floor = uint(visible.get("floor"), "visible.floor")
        require(initial_position <= floor <= prefix, "visible: floor is outside known model history")
        observed_events = []
        for event in array(visible.get("events"), "visible.events", MAX_OPERATIONS):
            event = obj(event, "visible.event")
            event_position = uint(event.get("position"), "visible.event.position")
            event_steps = []
            for mutation in array(event.get("mutations"), "event.mutations", MAX_STEPS):
                normalized, _ = step(mutation, "event.mutation")
                require(normalized[0] in ("put", "delete"), "event contains a nonmutation")
                event_steps.append(normalized)
            observed_events.append((event_position, event_steps))
        require(observed_events == [(position, mutations) for position, mutations in model_events
                                    if floor < position <= prefix],
                "visible: events disagree with acknowledged atomic mutation order")
        visible_checks += 1
    counts = obj(record.get("counts", {}), "counts")
    for field, actual in (("operations", len(operations)), ("acknowledged_writes", writes),
                          ("definite_aborts", aborted), ("readonly_commits", committed - writes)):
        if field in counts:
            require(uint(counts[field], f"counts.{field}") == actual,
                    f"counts.{field} disagrees with recorded operations")
    return {"seed": seed, "source_sha": source, "engine_version": version,
            "configuration": configuration, "operations": len(operations),
            "committed_operations": committed, "definite_aborts": aborted,
            "mutating_commits": writes, "wrote_flags_checked": flags,
            "model_snapshots": len(snapshots), "visible_heads_checked": visible_checks}


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_stream(path, expected_sha=None, expected_version=None, expected_count=None,
                  expected_first_seed=None, development=False, max_records=MAX_RECORDS):
    report = {"schema": 1, "tool": "independent_cerberus_witness_validator",
              "run_kind": "development" if development else "witness_validation",
              "input": str(path), "passed": False, "records_read": 0,
              "witnesses_validated": 0, "operations_validated": 0,
              "committed_operations": 0, "definite_aborts": 0, "mutating_commits": 0,
              "wrote_flags_checked": 0, "model_snapshots_built": 0,
              "visible_heads_checked": 0, "engine_executed": False,
              "search_performed": False, "absence_of_a_witness_proved": False,
              "historical_predicates_rechecked": False,
              "unstored_quiescent_results_rechecked": False,
              "scope": "validate the supplied witness and stored quiescent head/events only",
              "limits": {"line_bytes": MAX_LINE_BYTES, "operations_per_record": MAX_OPERATIONS,
                         "steps_per_operation": MAX_STEPS, "records": max_records,
                         "logical_input_bytes_per_record": MAX_INPUT_CHARGE,
                         "logical_model_bytes": MAX_MODEL_CHARGE, "model_rows": MAX_MODEL_ROWS},
              "limitations": ["no engine/server implementation or Rust checker is invoked",
                              "no search, exhaustive proof or inference of omitted operations",
                              "recorded source/version metadata is checked, not authenticated",
                              "historical predicates and unstored live-check responses are not replayed",
                              "equal clock ticks conservatively denote overlapping intervals"]}
    logical_digest = hashlib.sha256()
    logical_bytes = 0
    baseline = None
    exhausted = False
    current_seed = None
    try:
        path = Path(path)
        report["validator_sha256"] = file_hash(Path(__file__))
        before = path.stat()
        report["input_bytes"] = before.st_size
        report["input_sha256"] = file_hash(path)
        with path.open("rb") as probe:
            compressed = probe.read(2) == b"\x1f\x8b"
        report["gzip_input"] = compressed
        opener = gzip.open if compressed else open
        with opener(path, "rb") as source:
            while True:
                line = source.readline(MAX_LINE_BYTES + 1)
                if not line:
                    exhausted = True
                    break
                current_seed = None
                report["records_read"] += 1
                logical_digest.update(line)
                logical_bytes += len(line)
                require(report["records_read"] <= max_records, "record-count limit exceeded")
                require(len(line) <= MAX_LINE_BYTES, "JSONL line exceeds 2MiB limit")
                record = json.loads(line, object_pairs_hook=no_duplicate_keys)
                if type(record) is dict and type(record.get("workload")) is dict:
                    possible = record["workload"].get("spec")
                    if type(possible) is dict and type(possible.get("seed")) is int:
                        current_seed = possible["seed"]
                checked = validate_record(record)
                if baseline is None:
                    baseline = checked
                    require(expected_sha is None or checked["source_sha"] == expected_sha,
                            "first record does not match expected source SHA")
                    require(expected_version is None or checked["engine_version"] == expected_version,
                            "first record does not match expected engine version")
                    require(expected_first_seed is None or checked["seed"] == expected_first_seed,
                            "first record does not match expected seed")
                else:
                    require(checked["source_sha"] == baseline["source_sha"], "source SHA changed within stream")
                    require(checked["engine_version"] == baseline["engine_version"],
                            "engine version changed within stream")
                    require(checked["configuration"] == baseline["configuration"],
                            "workload configuration changed within stream")
                seed = (baseline["seed"] + report["witnesses_validated"]) & U64_MAX
                require(checked["seed"] == seed, "nonconsecutive or duplicate seed in stream")
                report["witnesses_validated"] += 1
                for field in ("committed_operations", "definite_aborts", "mutating_commits",
                              "wrote_flags_checked", "visible_heads_checked"):
                    report[field] += checked[field]
                report["operations_validated"] += checked["operations"]
                report["model_snapshots_built"] += checked["model_snapshots"]
        after = path.stat()
        require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
                "input changed during validation")
        require(report["witnesses_validated"] > 0, "empty input supplies no witnesses")
        require(expected_count is None or report["witnesses_validated"] == expected_count,
                "actual witness count does not match expected count")
        report["passed"] = True
    except (InvalidWitness, OSError, EOFError, ValueError, KeyError, TypeError, RecursionError) as error:
        report["failure"] = {"record_number": report["records_read"],
                             "seed": current_seed,
                             "message": str(error), "classification": "invalid_or_unvalidated_witness"}
    report["jsonl_bytes_read"] = logical_bytes
    report["jsonl_sha256"] = logical_digest.hexdigest()
    report["jsonl_digest_scope"] = ("complete_decompressed_stream" if exhausted
                                    else "prefix_read_before_failure")
    if baseline is not None:
        report.update({key: baseline[key] for key in ("source_sha", "engine_version")})
        report["first_seed"] = baseline["seed"]
    report["challenge_history_count_reached"] = report["passed"] and report["witnesses_validated"] >= 10_000
    report["full_release_qualification_claimed"] = False
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--expected-sha")
    parser.add_argument("--expected-version")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--expected-first-seed", type=int)
    parser.add_argument("--max-records", type=int, default=MAX_RECORDS)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not 1 <= args.max_records <= MAX_RECORDS:
        parser.error("max-records must be 1..100000")
    if args.expected_count is not None and not 1 <= args.expected_count <= args.max_records:
        parser.error("expected-count must be positive and within max-records")
    if args.expected_first_seed is not None and not 0 <= args.expected_first_seed <= U64_MAX:
        parser.error("expected-first-seed must be u64")
    if args.expected_sha is not None and re.fullmatch(r"[0-9a-f]{40}", args.expected_sha) is None:
        parser.error("expected-sha must be an exact lowercase Git SHA")
    if args.report is not None and args.report.exists():
        parser.error("report destination already exists; preserve earlier evidence")
    report = verify_stream(args.trace, args.expected_sha, args.expected_version,
                           args.expected_count, args.expected_first_seed,
                           args.development, args.max_records)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.report is not None:
        with args.report.open("x") as output:
            output.write(rendered)
    sys.stdout.write(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
