#!/usr/bin/env python3
"""Independently validate recorded Atlas observations; never infer actual execution."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

MAX_LINE_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 100000
PROFILES = {"loss-delay-reorder", "asymmetric-leader-change", "interrupted-snapshot"}
RECORDER_ONLY_COUNTERS = {"message_reorders", "historical_pages"}


class AuditError(ValueError):
    pass


def reject_constants(value):
    raise AuditError(f"nonfinite JSON number {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"duplicate JSON field {key}")
        result[key] = value
    return result


def strict_json(data):
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constants)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(value, label):
    if type(value) is not int or value < 0 or value > 2**64 - 1:
        raise AuditError(f"invalid nonnegative u64 {label}")
    return value


def byte_string(value):
    if not isinstance(value, list) or any(type(byte) is not int or not 0 <= byte <= 255 for byte in value):
        raise AuditError("invalid byte array")
    return bytes(value)


def rows(value):
    if not isinstance(value, list):
        raise AuditError("invalid row list")
    parsed = []
    previous = None
    for row in value:
        if not isinstance(row, list) or len(row) != 2:
            raise AuditError("invalid byte-key row")
        key, data = byte_string(row[0]), byte_string(row[1])
        if previous is not None and key <= previous:
            raise AuditError("rows contain duplicates or violate byte-key ordering")
        parsed.append((key, data))
        previous = key
    return parsed


def position(value):
    if not isinstance(value, dict) or set(value) != {"index", "term"}:
        raise AuditError("invalid index/term position")
    index = number(value["index"], "position index")
    term = number(value["term"], "position term")
    if (index == 0) != (term == 0):
        raise AuditError("index and term must both be zero or nonzero")
    return index, term


def chosen_requests(history):
    chosen = {}
    initial_position = position(history["initial"]["position"])[0]
    for op in history["operations"]:
        call, outcome = op["call"], op["outcome"]
        if call["call"] == "write" and outcome["outcome"] == "receipt":
            index, _ = position(outcome["position"])
            value = (call["request_id"], call["intent"], outcome["status"])
            if index in chosen and chosen[index] != value:
                raise AuditError("different named writes share or change one original receipt")
            chosen[index] = value
    return initial_position, sorted(chosen.items())


def reference_prefix(history, index, chosen):
    origin, requests = chosen
    if index < origin:
        raise AuditError("stored historical position predates the supplied reference anchor")
    state = dict(rows(history["initial"]["rows"]))
    for sequence, (_, intent, status) in requests:
        if sequence <= origin:
            continue
        if sequence > index:
            break
        condition = all(state.get(byte_string(expected["key"])) ==
                        (None if expected["value"] is None else byte_string(expected["value"]))
                        for expected in intent["expected"])
        if status not in {"applied", "conflict"} or condition != (status == "applied"):
            raise AuditError("independent historical conditional outcome mismatch")
        if status == "applied":
            for mutation in intent["mutations"]:
                key = byte_string(mutation["key"])
                if mutation["mutation"] == "put":
                    state[key] = byte_string(mutation["value"])
                elif mutation["mutation"] == "delete":
                    state.pop(key, None)
                else:
                    raise AuditError("unsupported reference mutation")
    return state


def historical(event, history, chosen):
    index, _ = position(event["position"])
    state = reference_prefix(history, index, chosen)
    expected = sorted(state.items())
    if rows(event["all_paginated_rows"]) != expected:
        raise AuditError("independent historical full-range reference mismatch")
    seen = set()
    for key, value in event["points"]:
        key = byte_string(key)
        if key in seen:
            raise AuditError("duplicate point observation key")
        seen.add(key)
        if (None if value is None else byte_string(value)) != state.get(key):
            raise AuditError("independent historical point reference mismatch")
    bounded = [(key, value) for key, value in expected if b"pair/" <= key < b"pair0"]
    if rows(event["bounded_range_rows"]) != bounded:
        raise AuditError("independent historical byte-range reference mismatch")
    typed, text = [], []
    for key, raw in expected:
        # These generated values use only small exact numeric classes. This is
        # deliberately not a general floating-point implementation of JSON.
        try:
            value = strict_json(raw)
        except (ValueError, UnicodeDecodeError):
            value = None
        scalar = value.get("n") if isinstance(value, dict) else None
        if type(scalar) in (int, float) and scalar == 1:
            typed.append((key, raw))
        try:
            words = "".join(character.lower() if character.isalnum() else " "
                            for character in raw.decode("utf-8")).split()
        except UnicodeDecodeError:
            words = []
        if "atlas" in words and "shared" in words:
            text.append((key, raw))
    if rows(event["typed_json_n_equals_1_float"]) != typed:
        raise AuditError("independent stored typed JSON equality reference mismatch")
    if rows(event["text_all_atlas_shared"]) != text:
        raise AuditError("independent stored whole-word text reference mismatch")


def check_message(message, cluster_id):
    if byte_string(message["partition"]).hex() != cluster_id:
        raise AuditError("protocol message belongs to another cluster identity")
    members = message["members"]
    if (not isinstance(members, list) or len(members) != 3
            or any(type(member) is not int or member <= 0 for member in members)
            or members != sorted(set(members))):
        raise AuditError("invalid recorded three-voter membership")
    number(message["from"], "message source")
    number(message["to"], "message destination")
    if message["from"] not in members or message["to"] not in members or message["from"] == message["to"]:
        raise AuditError("invalid recorded transport endpoint")
    if len(message["policy"]) != 5:
        raise AuditError("missing recorded application policy")
    for item in message["policy"]:
        number(item, "application policy")
    body = message["body"]
    if not isinstance(body, dict) or body["kind"] not in {"vote", "voted", "append", "appended", "install", "installed"}:
        raise AuditError("unsupported stored protocol message")
    if number(body["term"], "protocol term") == 0:
        raise AuditError("zero protocol term")
    if body["kind"] == "append":
        position(body["previous"])
        number(body["commit"], "announced commit")
        for entry in body["entries"]:
            position(entry["position"])
            byte_string(entry["data"])
    if body["kind"] == "install":
        position(body["position"])
        data = byte_string(body["data"])
        total = number(body["total"], "snapshot length")
        offset = number(body["offset"], "snapshot offset")
        if not data or offset > total or len(data) > total - offset:
            raise AuditError("invalid recorded snapshot chunk boundary")


def audit_record(envelope, expected_source, expected_version):
    if envelope["schema"] != 1 or envelope["source_sha"] != expected_source:
        raise AuditError("unexpected record schema/source SHA")
    record = envelope["record"]
    history, spec = record["history"], record["spec"]
    if history["schema"] != 1 or history["engine_version"] != expected_version:
        raise AuditError("unexpected history schema/engine version")
    if not re.fullmatch(r"[0-9a-f]{32}", history["cluster_id"]):
        raise AuditError("missing canonical partition generation identity")
    if history["membership_generation"] != 0:
        raise AuditError("this raw-schedule audit supports only the captured initial membership generation")
    for key in ("seed", "history_id", "profile"):
        if history[key] != spec[key]:
            raise AuditError(f"history/spec {key} mismatch")
    number(history["seed"], "seed")
    number(history["history_id"], "history id")
    if history["profile"] not in PROFILES:
        raise AuditError("unrecognized generated fault profile")
    # The stored result is evidence to compare, never a substitute for rerunning
    # the public independent search below.
    if envelope["checker"]["status"] != "linearizable":
        raise AuditError("stored invalid/inconclusive/violation cannot count as a pass")
    operations = history["operations"]
    chosen = chosen_requests(history)
    terms = {}

    def observe_position(value):
        index, term = position(value)
        if index in terms and terms[index] != term:
            raise AuditError("conflicting recorded committed terms for one index")
        terms[index] = term

    observe_position(history["initial"]["position"])
    for op in operations:
        if op["outcome"]["outcome"] in {"receipt", "snapshot"}:
            observe_position(op["outcome"]["position"])
    sends, terminal = set(), set()
    invocations, responses = {}, {}
    observed = Counter()
    previous_tick, previous_message, previous_clock = 0, 0, 0
    epoch = None
    for event in record["schedule"]:
        tick = number(event["tick"], "schedule tick")
        if tick <= previous_tick:
            raise AuditError("schedule events do not strictly increase")
        previous_tick = tick
        kind = event["event"]
        if kind in {"send", "duplicate", "deliver", "drop", "delay"}:
            number(event["id"], "message identity")
        if kind in {"client_invocation", "client_response"}:
            clock = number(event["monotonic_nanos"], "recorded monotonic clock")
            if clock < previous_clock:
                raise AuditError("recorded monotonic client clock moved backwards")
            previous_clock = clock
        if kind == "send":
            check_message(event["message"], history["cluster_id"])
            binding = (tuple(event["message"]["members"]), tuple(event["message"]["policy"]))
            if epoch is not None and binding != epoch:
                raise AuditError("recorded message membership/policy changes without supported generation")
            epoch = binding
            if event["id"] != previous_message + 1 or event["id"] in sends:
                raise AuditError("duplicate/nonconsecutive recorded message identity")
            previous_message = event["id"]
            sends.add(event["id"])
            observed["message_sends"] += 1
        elif kind == "duplicate":
            number(event["original"], "duplicate original identity")
            if event["original"] not in sends or event["id"] != previous_message + 1 or event["id"] in sends:
                raise AuditError("duplicate lacks an existing original message or unique identity")
            previous_message = event["id"]
            sends.add(event["id"])
            observed["message_duplicates"] += 1
        elif kind in {"deliver", "drop", "delay"}:
            if event["id"] not in sends or event["id"] in terminal:
                raise AuditError("transport action lacks an outstanding recorded message")
            if kind != "delay":
                terminal.add(event["id"])
            observed[{"deliver": "message_deliveries", "drop": "message_drops", "delay": "message_delays"}[kind]] += 1
            if kind == "deliver" and number(event["reordered_from_offset"], "delivery reorder offset"):
                observed["delivery_reorder_observations"] += 1
        elif kind == "leader_elected":
            observed["leader_elections"] += 1
            if type(event["replaces_previous_leader"]) is not bool:
                raise AuditError("invalid recorded leadership transition flag")
            observed["leadership_changes"] += int(event["replaces_previous_leader"])
        elif kind == "restart_durable_replica":
            observed["restarts"] += 1
        elif kind == "compact":
            observed["compactions"] += 1
        elif kind == "interrupted_snapshot_after_first_chunk":
            observed["interrupted_snapshots"] += 1
        elif kind == "historical_parity":
            observe_position(event["position"])
            historical(event, history, chosen)
            observed["historical_positions"] += 1
            observed["historical_point_reads"] += len(event["points"])
            observed["historical_searches"] += 1
        elif kind == "historical_expired":
            requested, _ = position(event["requested"])
            if requested >= event["floor"]:
                raise AuditError("stored expiry request is not below its declared floor")
            observed["historical_expired_errors"] += 1
        elif kind == "client_invocation":
            if event["operation"] in invocations:
                raise AuditError("duplicate client invocation")
            invocations[event["operation"]] = event
        elif kind == "client_response":
            if event["operation"] in responses:
                raise AuditError("duplicate client response")
            responses[event["operation"]] = event
        elif kind not in {"campaign", "logical_tick", "isolate", "heal_all_links", "asymmetric_link", "cluster_configuration"}:
            raise AuditError(f"unsupported recorded schedule event {kind}")
    if sends != terminal:
        raise AuditError("complete stored schedule leaves unresolved message identities")
    if len(operations) != len(invocations) or len(operations) != len(responses):
        raise AuditError("client intervals are missing from stored schedule")
    request_ids = set()
    operation_ids = set()
    for op in operations:
        if op["id"] in operation_ids:
            raise AuditError("duplicate operation id")
        operation_ids.add(op["id"])
        begin, end = invocations[op["id"]], responses[op["id"]]
        if (op["invocation"] != begin["tick"] or op["response"] != end["tick"]
                or op["invocation"] >= op["response"] or op["node"] != begin["node"]
                or op["client"] != begin["client"] or op["call"] != begin["call"]
                or op["outcome"] != end["outcome"]
                or number(begin["monotonic_nanos"], "invocation clock") > number(end["monotonic_nanos"], "response clock")):
            raise AuditError("checker interval differs from recorded client boundary")
        observed["client_operations"] += 1
        call = op["call"]
        if call["call"] == "read":
            observed["quorum_reads" if call["mode"] == "quorum" else "local_reads"] += 1
        elif call["call"] == "write":
            if call["request_id"] in request_ids:
                observed["named_retries"] += 1
            request_ids.add(call["request_id"])
            if op["outcome"]["outcome"] == "unknown":
                observed["unknown_writes"] += 1
    counts = record["counts"]
    comparable = set(counts) - RECORDER_ONLY_COUNTERS
    for key in comparable:
        if number(counts[key], f"reported {key}") != observed[key]:
            raise AuditError(f"stored observation counter mismatch: {key}")
    if number(counts.get("message_reorders", 0), "reported reorders") < observed["delivery_reorder_observations"]:
        raise AuditError("reported reorders below stored reordered deliveries")
    return history, observed, sorted(set(counts) & RECORDER_ONLY_COUNTERS)


def new_file(path):
    path = Path(path)
    if path.exists():
        raise AuditError(f"destination must be new: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_response(process):
    line = process.stdout.readline(MAX_LINE_BYTES + 1)
    if not line or len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
        raise AuditError("checker response missing, truncated or oversized")
    return strict_json(line)


def verify(args):
    report_path = new_file(args.report)
    witness_path = new_file(args.witnesses or str(report_path.with_suffix(".witnesses.jsonl.gz")))
    if report_path.resolve() == witness_path.resolve():
        raise AuditError("report and witness destinations must differ")
    checker = Path(args.checker).resolve()
    if not checker.is_file():
        raise AuditError("standalone checker executable missing")
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_source):
        raise AuditError("expected source must be an exact canonical Git SHA")
    if not 1 <= args.expected_count <= MAX_RECORDS:
        raise AuditError("expected count must be 1..100000")
    if args.sha256 and len(args.sha256) != len(args.inputs):
        raise AuditError("supply one --sha256 for every input, or omit all")
    report = {"schema": 1, "tool": "atlas-recorded-observation-audit", "tool_version": "0.1.0",
              "utc": datetime.now(timezone.utc).isoformat(), "all_recorded_observations_consistent": False,
              "expected_source_sha": args.expected_source, "expected_engine_version": args.expected_version,
              "expected_records": args.expected_count, "audit_python_sha256": digest_file(__file__),
              "checker_executable_sha256": digest_file(checker),
              "claims": {"actual_engine_execution_verified": False, "capture_completeness_verified": False,
                         "cross_host_faults_verified": False, "release_qualification": False},
              "limitations": ["Validates supplied recorded observations against independent reference models; source labels and capture authenticity are not authenticated.",
                              "Transport events are recorded schedules, not independently witnessed deliveries or process terminations.",
                              "Historical checks cover stored point values, concatenated byte-range rows, typed n==1.0 and whole-word ATLAS shared results only.",
                              "Individual page boundaries/cursors, unrecorded queries, wall-clock behavior, storage survival and deployment faults are not inferred.",
                              "Local reads are committed-prefix consistency observations; only explicitly quorum reads receive the interval linearizability check."],
              "inputs": [], "records_checked": 0}
    totals, profiles = Counter(), Counter()
    identifiers, seeds = set(), set()
    unverified = set()
    history_digest = hashlib.sha256()
    checker_digest = hashlib.sha256()
    process = None
    error = None
    try:
        process = subprocess.Popen([str(checker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        with witness_path.open("xb") as raw_witness:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_witness, mtime=0) as witnesses:
                for input_index, raw_path in enumerate(args.inputs):
                    path = Path(raw_path).resolve()
                    file_hash = digest_file(path)
                    if args.sha256 and file_hash != args.sha256[input_index]:
                        raise AuditError("input file SHA-256 mismatch")
                    item = {"path": str(path), "file_sha256": file_hash, "records": 0,
                            "decompressed_complete": False}
                    report["inputs"].append(item)
                    expanded_digest = hashlib.sha256()
                    with path.open("rb") as raw:
                        magic = raw.read(2)
                        raw.seek(0)
                        stream = gzip.GzipFile(fileobj=raw) if magic == b"\x1f\x8b" else raw
                        try:
                            while True:
                                line = stream.readline(MAX_LINE_BYTES + 1)
                                if not line:
                                    break
                                if len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
                                    raise AuditError("input line exceeds 16MiB or is not newline-terminated")
                                expanded_digest.update(line)
                                envelope = strict_json(line)
                                history, observed, reported_only = audit_record(envelope, args.expected_source, args.expected_version)
                                if history["history_id"] in identifiers or history["seed"] in seeds:
                                    raise AuditError("duplicate recorded history identity/seed across input files")
                                identifiers.add(history["history_id"])
                                seeds.add(history["seed"])
                                if len(identifiers) > MAX_RECORDS:
                                    raise AuditError("more than 100000 records")
                                payload = canonical(history) + b"\n"
                                if len(payload) > MAX_LINE_BYTES:
                                    raise AuditError("canonical history exceeds 16MiB")
                                process.stdin.write(payload)
                                process.stdin.flush()
                                checked = read_response(process)
                                expected_line = report["records_checked"] + 1
                                if (checked.get("type") != "record" or checked.get("line") != expected_line
                                        or checked.get("history_id") != history["history_id"] or checked.get("seed") != history["seed"]):
                                    raise AuditError("checker response does not match the submitted history")
                                if checked["result"]["status"] != "linearizable":
                                    raise AuditError(f"independent checker did not pass: {checked['result']}")
                                history_digest.update(payload)
                                result_payload = canonical(checked)
                                checker_digest.update(result_payload + b"\n")
                                witnesses.write(canonical({"schema": 1, "line": expected_line,
                                    "history_id": history["history_id"], "seed": history["seed"],
                                    "history_canonical_sha256": hashlib.sha256(payload).hexdigest(),
                                    "raw_record_sha256": hashlib.sha256(line).hexdigest(),
                                    "checker_response_sha256": hashlib.sha256(result_payload).hexdigest(),
                                    "checker": checked}) + b"\n")
                                totals.update(observed)
                                profiles[history["profile"]] += 1
                                unverified.update(reported_only)
                                report["records_checked"] += 1
                                item["records"] += 1
                            item["decompressed_complete"] = True
                        finally:
                            item["decompressed_sha256"] = expanded_digest.hexdigest()
                            if stream is not raw:
                                stream.close()
        if report["records_checked"] != args.expected_count:
            raise AuditError("record count differs from exact expected count")
        process.stdin.close()
        summary = read_response(process)
        stderr = process.stderr.read(65537)
        code = process.wait()
        if (len(stderr) > 65536 or code != 0 or summary.get("type") != "summary"
                or not summary.get("all_passed") or summary.get("records") != args.expected_count
                or summary.get("linearizable") != args.expected_count):
            raise AuditError(f"standalone checker summary/exit did not pass: exit={code} summary={summary} stderr={stderr.decode(errors='replace')}")
        if process.stdout.read(1):
            raise AuditError("unexpected output after checker summary")
        report["standalone_checker_summary"] = summary
        report["all_recorded_observations_consistent"] = True
    except (OSError, ValueError, KeyError, TypeError, EOFError, BrokenPipeError) as failure:
        error = str(failure)
        report["failure"] = error
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed:
                    try:
                        stream.close()
                    except OSError:
                        pass
        report["profiles"] = dict(profiles)
        report["independently_recounted_stored_observations"] = dict(totals)
        report["recorder_only_counters_not_independently_recounted"] = sorted(unverified)
        report["canonical_histories_complete"] = error is None
        report["canonical_histories_sha256"] = history_digest.hexdigest()
        report["checker_responses_sha256"] = checker_digest.hexdigest()
        if witness_path.is_file():
            report["witnesses"] = {"path": str(witness_path.resolve()), "sha256": digest_file(witness_path)}
        with report_path.open("x") as out:
            json.dump(report, out, indent=2, sort_keys=True)
            out.write("\n")
    if error is not None:
        raise AuditError(error)
    print(json.dumps({"records_checked": report["records_checked"],
                      "all_recorded_observations_consistent": True,
                      "report": str(report_path), "report_sha256": digest_file(report_path)}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--checker", required=True, help="Built standalone atlas-history-checker executable")
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--sha256", action="append", help="Optional exact compressed/plain file hash, one per input in order")
    parser.add_argument("--report", required=True, help="New JSON destination")
    parser.add_argument("--witnesses", help="New gzip JSONL destination; defaults beside report")
    verify(parser.parse_args())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as failure:
        print(f"audit-atlas-traces: {failure}", file=sys.stderr)
        sys.exit(1)
