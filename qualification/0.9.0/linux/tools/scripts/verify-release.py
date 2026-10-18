#!/usr/bin/env python3
"""Verify archive inventory before extraction; optionally exercise the actual binaries."""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zlib

BINS = ("polybase", "polybase-console", "polybase-node", "polybase-cluster-console", "polybase-stdio")
FILES = {*(f"bin/{binary}" for binary in BINS), "LICENSE", "GUARANTEES.md", "README.md",
         "REPLICATION.md", "docs/SEARCH.md", "scripts/start-local-cluster.py", "scripts/cluster_driver.py",
         "THIRD_PARTY_NOTICES.txt", "docs/PREVIEW_0_7.md", "clients/README.md",
         "clients/typescript/client.ts", "clients/rust/src/lib.rs", "scripts/fault-lab-v2.py", "docs/PREVIEW_0_8.md", "docs/PREVIEW_0_8_2.md", "docs/JANUS_0_9.md"}
TARGETS = {"aarch64-apple-darwin", "x86_64-unknown-linux-gnu"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


@contextmanager
def checked_tar(archive):
    """Bound inflation and validate ordinary USTAR headers before tarfile sees them."""
    maximum = 128 * 1024 * 1024
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    with archive.open("rb") as raw, tempfile.TemporaryFile() as stream:
        require(raw.read(4) == b"\x1f\x8b\x08\x00", "package gzip header must not contain optional fields")
        raw.seek(0)
        inflated = 0
        while chunk := raw.read(64 * 1024):
            while chunk:
                data = decoder.decompress(chunk, min(1024 * 1024, maximum - inflated + 1))
                inflated += len(data)
                require(inflated <= maximum, "decompressed archive exceeds bound")
                stream.write(data)
                chunk = decoder.unconsumed_tail
                if decoder.eof:
                    require(not chunk and not decoder.unused_data and not raw.read(1),
                            "extra gzip member or compressed trailer")
                    break
            if decoder.eof:
                break
        require(decoder.eof, "incomplete gzip stream")
        require(inflated % tarfile.RECORDSIZE == 0, "noncanonical tar record padding")
        stream.seek(0)
        count = 0
        while True:
            header = stream.read(tarfile.BLOCKSIZE)
            require(len(header) == tarfile.BLOCKSIZE, "missing tar termination")
            if header == bytes(tarfile.BLOCKSIZE):
                require(stream.read(tarfile.BLOCKSIZE) == bytes(tarfile.BLOCKSIZE), "invalid tar termination")
                padding = stream.read(tarfile.RECORDSIZE + 1)
                require(len(padding) <= tarfile.RECORDSIZE and not any(padding) and not stream.read(1),
                        "hidden tar payload or excessive padding")
                break
            require(header[156:157] == tarfile.REGTYPE and header[257:265] == b"ustar\x0000",
                    "unsupported tar extension or entry type")
            member = tarfile.TarInfo.frombuf(header, encoding="utf-8", errors="strict")
            require(member.tobuf(format=tarfile.USTAR_FORMAT, encoding="utf-8", errors="strict") == header,
                    "noncanonical tar header contains unlisted bytes")
            count += 1
            require(count <= len(FILES) + 1 and 0 <= member.size <= 32 * 1024 * 1024,
                    "raw tar inventory exceeds bound")
            extent = ((member.size + tarfile.BLOCKSIZE - 1) // tarfile.BLOCKSIZE) * tarfile.BLOCKSIZE
            require(stream.tell() + extent <= inflated, "truncated tar entry")
            stream.seek(member.size, 1)
            require(not any(stream.read(extent - member.size)), "hidden member padding payload")
        stream.seek(0)
        yield stream


def verify(archive, expected=None, allow_dirty=False):
    require(archive.stat().st_size < 128 * 1024 * 1024, "compressed archive too large")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(archive.suffix + ".sha256").read_text().split()
    require(checksum == [digest, archive.name], "archive checksum file mismatch")
    if expected:
        require(digest == expected, "archive does not match independently supplied SHA-256")
    with checked_tar(archive) as stream, tarfile.open(fileobj=stream, mode="r:") as tar:
        members = []
        for member in tar:
            require(len(members) < len(FILES) + 1 and member.size <= 32 * 1024 * 1024,
                    "archive exceeds bounded inventory")
            members.append(member)
        require(len(members) == len(FILES) + 1, "unexpected archive member count")
        require(len({member.name for member in members}) == len(members), "duplicate archive path")
        require(sum(member.size for member in members) < 128 * 1024 * 1024, "archive too large")
        roots = set()
        for member in members:
            path = PurePosixPath(member.name)
            require(member.isfile() and 0 <= member.size <= 32 * 1024 * 1024, "unsafe archive entry")
            require(not path.is_absolute() and ".." not in path.parts and len(path.parts) >= 2,
                    "unsafe archive path")
            require(str(path) == member.name, "noncanonical archive path")
            roots.add(path.parts[0])
        require(len(roots) == 1, "archive must have one root")
        root = next(iter(roots))
        manifest_member = tar.getmember(f"{root}/manifest.json")
        require(manifest_member.size <= 256 * 1024, "manifest exceeds bound")
        manifest = json.loads(tar.extractfile(manifest_member).read())
        require(manifest["schema"] == 1 and manifest["product"] == "Polybase", "wrong product/schema")
        require(manifest["target"] in TARGETS, "unsupported target")
        require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-preview\.[0-9]+)?", manifest["version"]), "invalid release version")
        require(root == f"polybase-{manifest['version']}-{manifest['target']}", "wrong archive root")
        require(archive.name == f"{root}.tar.gz", "wrong archive filename")
        require(re.fullmatch(r"[a-f0-9]{40}", manifest["source_commit"]), "missing source revision")
        require(manifest["source_dirty"] is False or allow_dirty, "dirty-source package cannot be released")
        require(manifest["build_features"] == [], "release must not enable fault-injection")
        inventory = {item["path"]: item for item in manifest["files"]}
        require(len(inventory) == len(manifest["files"]) and set(inventory) == FILES, "inventory mismatch")
        require({member.name for member in members} == {f"{root}/{file}" for file in FILES | {"manifest.json"}},
                "archive contains non-allowlisted files")
        contents = {}
        for member in members:
            name = str(PurePosixPath(member.name).relative_to(root))
            data = tar.extractfile(member).read()
            if name != "manifest.json":
                item = inventory[name]
                require(item["bytes"] == len(data) and item["sha256"] == hashlib.sha256(data).hexdigest(),
                        f"content mismatch: {name}")
                require(item["mode"] == oct(member.mode), f"mode mismatch: {name}")
            expected_mode = 0o755 if name.startswith("bin/") else 0o644
            require(member.mode == expected_mode, f"unexpected permissions: {name}")
            if name.startswith("bin/"):
                if manifest["target"] == "aarch64-apple-darwin":
                    require(data[:8] == b"\xcf\xfa\xed\xfe\x0c\x00\x00\x01", "expected arm64 Mach-O")
                else:
                    require(data[:6] == b"\x7fELF\x02\x01" and data[18:20] == b"\x3e\x00", "expected x86-64 ELF")
            contents[name] = (data, member.mode)
        for dependency in manifest["dependencies"]:
            require(dependency["notice_files"] and dependency["license"], "missing dependency license")
            require(f"{dependency['name']} {dependency['version']}".encode() in contents["THIRD_PARTY_NOTICES.txt"][0],
                    "missing dependency notice")
        require(b"](docs/SEARCH.md)" in contents["README.md"][0]
                and b"](docs/SEARCH.md)" in contents["GUARANTEES.md"][0],
                "packaged search guide links are broken")
    return manifest, contents, digest


def api(base, path, body=None, expected=200, origin=None):
    request = urllib.request.Request(base + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Origin": origin or base})
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        require(response.status == expected, f"{path}: HTTP {response.status}, expected {expected}")
        return json.load(response)


@contextmanager
def console(stage, db):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with (stage / f"console-{port}.log").open("wb") as log:
        process = subprocess.Popen([str(stage / "bin/polybase-console"), str(db), str(port)], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 15
            while True:
                require(process.poll() is None, "packaged console exited during startup")
                try:
                    api(base, "/api/health")
                    break
                except (OSError, ValueError):
                    require(time.monotonic() < deadline, "packaged console startup deadline")
                    time.sleep(0.05)
            yield base
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def console_checks(stage, db):
    with console(stage, db) as base:
        health = api(base, "/api/health")
        require(health["head"] == "1" and health["keys"] == 2, "wrong console recovered prefix")
        query = api(base, "/api/query", {"key_prefix": "", "predicate": "any", "value": ""})
        require(len(query["rows"]) == 2, "wrong initial query snapshot")
        token = api(base, "/api/request", {})["request_token"]
        batch = {"request_token": token, "reads": [{"key": "70726f6a656374732f63", "value": None}],
                 "mutations": [{"key": "70726f6a656374732f63", "value": "616374697665"}]}
        # Discard the first receipt, then reconcile the exact submitted identity.
        api(base, "/api/commit", batch)
        require(api(base, "/api/outcome", {"token": token})["position"] == "2", "lost receipt not recoverable")
        replay = api(base, "/api/commit", batch)
        require(replay["replayed"] and replay["durable"] and replay["position"] == "2", "request replay changed outcome")
        page = api(base, "/api/poll", {"id": query["id"], "instance": query["instance"], "token": query["token"]})
        require(len(page["commits"]) == 1 and len(page["commits"][0]["changes"]) == 1, "duplicated request event")
        stale = {**batch, "request_token": api(base, "/api/request", {})["request_token"]}
        require(api(base, "/api/commit", stale, expected=409)["code"] == "conflict", "stale expectation accepted")
        api(base, "/api/request", {}, expected=403, origin="https://unrelated.invalid")
        api(base, "/api/checkpoint", {})
        api(base, "/api/close", {})
    with console(stage, db) as base:
        require(api(base, "/api/outcome", {"token": token})["position"] == "2", "receipt lost at checkpoint/restart")
        require(api(base, "/api/health")["head"] == "2", "replay created another durable event")
        api(base, "/api/close", {})
    return ["packaged loopback console and query deltas", "discarded receipt reconciles original request",
            "same-token retry has one event", "stale edit and foreign origin reject",
            "checkpoint/restart preserves state and receipt"]


def collection_checks(stage, run):
    db = stage / "collections-db"
    run("polybase", "init", db)
    task = '{"title":"Write a note","done":false}'
    note = "A first note: café 📝"
    run("polybase", "batch", db, "put", "tasks/1", task, "put", "notes/1", note,
        "put", "sensors/room-a", '{"temperature":21.5}',
        "put", "tasks-archive/1", "a separate collection")
    require(run("polybase", "get", db, "tasks/1") == task + "\n", "JSON collection value changed")
    require(run("polybase", "get", db, "notes/1") == note + "\n", "Unicode collection value changed")
    key = lambda text: text.encode().hex()
    query_body = lambda prefix: {"key_prefix": key(prefix), "predicate": "any", "value": ""}
    completed = '{"title":"Write a note","done":true}'
    binary = "00ff0a"
    with console(stage, db) as base:
        tasks = api(base, "/api/query", query_body("tasks/"))
        notes = api(base, "/api/query", query_body("notes/"))
        json_search = {"kind": "json", "key_prefix": key("tasks/"), "path": ["done"], "value": False}
        text_search = {"kind": "text", "key_prefix": key("notes/"), "text": "CAFÉ"}
        found = api(base, "/api/search", json_search)
        require(found["position"] == "1" and found["indexed"]
                and found["rows"] == [{"key": key("tasks/1"), "value": key(task)}],
                "indexed JSON field search disagreed with committed task")
        found = api(base, "/api/search", text_search)
        require(found["position"] == "1" and found["indexed"]
                and found["rows"] == [{"key": key("notes/1"), "value": key(note)}],
                "Unicode whole-word search disagreed with committed note")
        require(tasks["rows"] == [{"key": key("tasks/1"), "value": key(task)}],
                "collection query included another prefix")
        require(notes["rows"] == [{"key": key("notes/1"), "value": key(note)}],
                "notes collection did not preserve its own value")
        require(len(api(base, "/api/query", query_body(""))["rows"]) == 4,
                "empty prefix must include every collection")
        token = api(base, "/api/request", {})["request_token"]
        api(base, "/api/commit", {
            "request_token": token,
            "reads": [{"key": key("tasks/1"), "value": key(task)},
                      {"key": key("notes/1"), "value": key(note)}],
            "mutations": [{"key": key("tasks/1"), "value": key(completed)},
                          {"key": key("notes/1"), "value": binary}]})
        for snapshot, expected_key in [(tasks, "tasks/1"), (notes, "notes/1")]:
            page = api(base, "/api/poll", {field: snapshot[field] for field in ("id", "instance", "token")})
            require(len(page["commits"]) == 1 and page["commits"][0]["position"] == "2",
                    "cross-collection batch must have one shared commit position")
            require(len(page["commits"][0]["changes"]) == 1
                    and page["commits"][0]["changes"][0]["key"] == key(expected_key),
                    "collection delta included another collection")
        require(api(base, "/api/search", json_search)["rows"] == [],
                "JSON field search retained stale posting after update")
        require(api(base, "/api/search", text_search)["rows"] == [],
                "text search retained stale posting after binary replacement")
        api(base, "/api/checkpoint", {})
        api(base, "/api/close", {})
    with console(stage, db) as base:
        require(api(base, "/api/query", query_body("tasks/"))["rows"] ==
                [{"key": key("tasks/1"), "value": key(completed)}], "task update did not recover")
        require(api(base, "/api/query", query_body("notes/"))["rows"] ==
                [{"key": key("notes/1"), "value": binary}], "binary note value did not recover")
        require(api(base, "/api/search", {**json_search, "value": True})["rows"] ==
                [{"key": key("tasks/1"), "value": key(completed)}],
                "JSON search did not rebuild after checkpoint/restart")
        api(base, "/api/close", {})
    return ["user-defined collections: JSON/text/hex, prefix isolation, cross-collection writes and restart",
            "extracted JSON-field and Unicode text search update and rebuild"]


def cluster_checks(stage):
    spec = importlib.util.spec_from_file_location("packaged_cluster", stage / "scripts/cluster_driver.py")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    cluster = driver.Cluster(stage / "cluster-acceptance", binary=stage / "bin/polybase-node")
    try:
        leader = cluster.leader()
        token = cluster.call(leader, {"op": "issue"})["request_token"]
        task_key = b"tasks/1".hex()
        note_key = b"notes/1".hex()
        intent = {"reads": [{"key": task_key, "value": None}, {"key": note_key, "value": None}],
                  "mutations": [{"key": task_key, "value": "73"}, {"key": note_key, "value": "73"}]}
        receipt = cluster.call(leader, {"op": "write", "token": token, "intent": intent})
        require(receipt["status"] == "applied" and receipt["durable"], "replicated write not acknowledged")
        expected = {task_key: "73", note_key: "73"}
        require({row["key"]: row["value"] for row in cluster.snapshot(leader, "quorum")["rows"]} == expected,
                "replicated atomic rows disagree")
        tasks = cluster.call(leader, {"op": "snapshot", "mode": "quorum", "minimum": None,
                                      "query": {"key_prefix": b"tasks/".hex(), "predicate": "any", "value": ""}})
        require(tasks["rows"] == [{"key": task_key, "value": "73"}],
                "replicated collection query included notes")
        cluster.kill(leader)
        replacement = cluster.leader(exclude=(leader,))
        outcome = cluster.call(replacement, {"op": "outcome", "token": token, "intent": intent})
        require(outcome["position"] == receipt["position"], "acknowledged receipt lost at failover")
        replay = cluster.call(replacement, {"op": "write", "token": token, "intent": intent})
        require(replay["position"] == receipt["position"], "retry chose a second original outcome")
        require({row["key"]: row["value"] for row in cluster.snapshot(replacement, "quorum")["rows"]} == expected,
                "failover state differs")
        cluster.spawn(leader)
        driver.wait_for(lambda: {row["key"]: row["value"] for row in cluster.snapshot(leader)["rows"]} == expected)
    finally:
        cluster.close()
    return ["three extracted node processes commit across collections with separate queries", "leader SIGKILL preserves acknowledged receipt",
            "same request reconciles and replays across failover", "restarted original voter catches up"]


def preview7_checks(stage, run):
    db = stage / "preview7-db"
    run("polybase", "init", db)
    query = {"key_prefix": "646f63732f", "predicate": "json", "value": "",
             "json": {"op": "ge", "path": ["score"], "value": 2}}
    with console(stage, db) as base:
        session = api(base, "/api/query", query)
        revision = api(base, "/api/read-revision", {"key": "646f63732f61"})["revision"]
        first = api(base, "/api/write-revision", {"revision": revision, "value": b'{"score":3}'.hex()})
        api(base, "/api/write-revision", {"revision": revision, "value": "00"}, expected=409)
        second = api(base, "/api/read-revision", {"key": "646f63732f62"})["revision"]
        api(base, "/api/write-revision", {"revision": second, "value": b'{"score":4}'.hex()})
        page = api(base, "/api/query-page", {"query": query, "cursor": None, "limit": 1})
        require(page["next"] and len(page["rows"]) == 1, "missing stable pagination")
        changed = api(base, "/api/read-revision", {"key": "646f63732f62"})["revision"]
        api(base, "/api/write-revision", {"revision": changed, "value": b'{"score":1}'.hex()})
        continuation = api(base, "/api/query-page", {"query": query, "cursor": page["next"], "limit": 1})
        require(continuation["position"] == page["position"] and continuation["rows"][0]["value"] == b'{"score":4}'.hex(), "pagination drifted")
        delta = api(base, "/api/poll", {"id": session["id"], "instance": session["instance"], "token": session["token"]})
        require(len(delta["commits"]) == 3 and delta["commits"][-1]["changes"][0]["after"] is None, "live typed JSON changes missing")
        api(base, "/api/unsubscribe", {"id": session["id"], "instance": session["instance"], "token": delta["token"]})
        historical = api(base, "/api/snapshot-at", {"position": first["position"]})
        require(len(historical["rows"]) == 1, "historical prefix mismatch")
        explain = api(base, "/api/explain", {"query": query, "cursor": None, "limit": 16})["explain"]
        require(explain["scanned_records"] == 0 and explain["scanned_rows"] == 2 and explain["matched_rows"] == 1, "incorrect actual query metrics")
        api(base, "/api/index-create", {"name": "score", "prefix": list(b"docs/"), "path": ["score"]})
        require(len(api(base, "/api/index-search", {"name": "score", "value": 3})["rows"]) == 1, "named index search failed")
        advice = api(base, "/api/compaction-advice", {"retain_commits": "100"})
        require(advice["suggested_floor"] == "0", "advisor violated requested history")
        backup = stage / "preview7-backup"
        receipt = api(base, "/api/backup", {"directory": str(backup)})
        require(receipt["verified"], "online backup unverified")
        require(api(base, "/api/verify-backup", {"directory": str(backup)})["position"] == receipt["position"], "backup verify position mismatch")
    with console(stage, db) as base:
        require(len(api(base, "/api/index-list", {})["indexes"]) == 1, "index definition lost after restart")
        # Keep the legacy index qualification selective under the new cost model.
        for item in range(20):
            key = f"docs/nonmatch-{item:02}".encode().hex()
            revision = api(base, "/api/read-revision", {"key": key})["revision"]
            api(base, "/api/write-revision", {"revision": revision, "value": b'{"score":0}'.hex()})
        typed = {"key_prefix":"646f63732f","predicate":"json","value":"",
                 "json":{"op":"all","predicates":[{"op":"eq","path":["score"],"value":3.0},{"op":"ge","path":["score"],"value":2}]}}
        body = {"query":typed,"cursor":None,"limit":16}
        planned=api(base,"/api/query-page",body)
        forced=api(base,"/api/query-page",{**body,"force_scan":True})
        explained=api(base,"/api/explain",body)
        require(planned["rows"]==forced["rows"] and len(planned["rows"])==1,"0.8 typed numeric equality/residual parity failed")
        require(planned["explain"]["plan"]=="index_lookup" and planned["explain"]["index_name"]=="score","0.8 index not used")
        require(forced["explain"]["plan"]=="scan" and forced["explain"]["fallback_reason"]=="forced_scan","0.8 forced scan not used")
        require(explained["rows"]==planned["rows"] and explained["explain"]["candidate_count"]==1,"0.8 explain/execution differ")
        api(base,"/api/index-drop",{"name":"score"})
        fallback=api(base,"/api/query-page",body)
        require(fallback["rows"]==planned["rows"] and fallback["explain"]["fallback_reason"]=="missing_index","0.8 dropped-index fallback lost rows")
        continuation = api(base, "/api/query-page", {"query": query, "cursor": page["next"], "limit": 1})
        require(continuation["position"] == page["position"], "cursor lost after restart")
    return ["0.7 typed live JSON, pagination, revisions, history, explain, indexes, backup and advisor across restart",
            "0.8 typed index planning, forced-scan parity, explain and dropped-index fallback across restart"]


def preview82_checks(stage, run):
    db = stage / "preview82-db"
    run("polybase", "init", db)
    batch = []
    for item in range(100):
        value = {"rare": item == 0, "broad": item < 90,
                 "a": item < 10, "b": item % 10 == 0}
        batch.extend(["put", f"docs/{item:03}", json.dumps(value, separators=(",", ":"))])
    run("polybase", "batch", db, *batch)
    eq = lambda name: {"op": "eq", "path": [name], "value": True}
    def query(predicate):
        return {"key_prefix": b"docs/".hex(), "predicate": "json", "value": "", "json": predicate}
    cases = [(eq("rare"), "index_lookup", 1), (eq("broad"), "scan", 90),
             ({"op": "all", "predicates": [eq("a"), eq("b")]}, "index_intersection", 1),
             ({"op": "any", "predicates": [eq("a"), eq("b")]}, "index_union", 19)]
    def check(base):
        for predicate, strategy, count in cases:
            body = {"query": query(predicate), "cursor": None, "limit": 128}
            planned = api(base, "/api/query-page", body)
            forced = api(base, "/api/query-page", {**body, "force_scan": True})
            require(planned["rows"] == forced["rows"] and len(planned["rows"]) == count,
                    "0.8.2 adaptive query/forced Scan parity failed")
            explain = planned["explain"]; optimizer = explain["optimizer"]
            require(optimizer["strategy"] == strategy, f"0.8.2 unexpected {strategy} choice")
            require(str(optimizer["statistics_epoch"]) == planned["position"], "statistics head mismatch")
            require(optimizer["alternatives"] and optimizer["estimated_work"] >= 0,
                    "0.8.2 missing work estimates")
            require(len({row["key"] for row in planned["rows"]}) == count, "0.8.2 duplicate candidates escaped")
            explained = api(base, "/api/explain", body)
            require(explained["rows"] == planned["rows"] and explained["explain"]["optimizer"]["strategy"] == strategy,
                    "0.8.2 EXPLAIN differs from ordinary execution")
    with console(stage, db) as base:
        for name in ["rare", "broad", "a", "b"]:
            api(base, "/api/index-create", {"name": name, "prefix": list(b"docs/"), "path": [name]})
        check(base)
        first = api(base, "/api/query-page", {"query": query(eq("broad")), "cursor": None, "limit": 7})
        require(first["next"] and len(first["rows"]) == 7, "0.8.2 pagination missing")
    with console(stage, db) as base:
        check(base)
        continuation = api(base, "/api/query-page", {"query": query(eq("broad")), "cursor": first["next"], "limit": 7})
        require(continuation["position"] == first["position"] and continuation["rows"][0]["key"] > first["rows"][-1]["key"],
                "0.8.2 historical continuation regressed")
    return ["0.8.2 selectivity-aware scan and lookup, AND intersection, OR union, explain, forced-scan parity and historical continuation across restart"]


def janus_checks(stage, run):
    db = stage / "janus-db"
    run("polybase", "init", db)
    a, b = '{"n":1,"text":"quick fox"}', '{"n":1.0,"text":"slow owl"}'
    run("polybase", "batch", db, "put", "docs/a", a, "put", "docs/b", b,
        "put", "text/a", "quick fox")
    key = lambda value: value.encode().hex()
    expected = [{"key": key("docs/a"), "value": key(a)}, {"key": key("docs/b"), "value": key(b)}]
    query = {"key_prefix": key("docs/"), "predicate": "json", "value": "",
             "json": {"op": "eq", "path": ["n"], "value": 1}}
    body = {"position": "1", "query": query, "cursor": None, "limit": 8}
    with console(stage, db) as base:
        point = api(base, "/api/as-of-get", {"position": "1", "key": key("docs/a")})
        require(point["value"] == key(a) and point["position"] == "1", "Janus historical point failed")
        require(api(base, "/api/as-of-get", {"position": "1", "key": key("absent")})["value"] is None,
                "Janus valid missing key was not empty")
        page = api(base, "/api/as-of-query", body)
        require(page["rows"] == expected and page["position"] == "1", "Janus typed historical JSON changed semantics")
        explain = api(base, "/api/as-of-explain", body)
        require(explain["rows"] == page["rows"] and explain["explain"]["history_position"] == "1",
                "Janus explain diverged from execution")
        for field in ("chosen_plan", "estimated_rows", "actual_rows", "plan_reason", "fallback_reason", "execution_stats"):
            require(field in explain["explain"], f"Janus missing diagnostic {field}")
        require(explain["explain"]["actual_rows"]["returned"] == 2, "Janus actual returned count incorrect")
        narrow = api(base, "/api/as-of-query", {**body, "range": {
            "start": {"included": key("docs/b")}, "end": {"excluded": key("docs/c")}}})
        require(narrow["rows"] == expected[1:], "Janus historical range bound incorrect")
        text = api(base, "/api/as-of-search", {"position": "1", "query": {
            "kind": "text", "key_prefix": key("text/"), "text": "quick fox"}, "limit": 8})
        require(text["rows"] == [{"key": key("text/a"), "value": key("quick fox")}],
                "Janus historical whole-word search failed")
        first = api(base, "/api/as-of-query", {**body, "limit": 1})
        require(first["next"] and first["rows"] == expected[:1], "Janus historical pagination missing")
        write = api(base, "/api/commit", {
            "reads": [{"key": key("docs/b"), "value": key(b)}, {"key": key("text/a"), "value": key("quick fox")}],
            "mutations": [{"key": key("docs/b"), "value": key('{"n":9}')},
                          {"key": key("text/a"), "value": key("slow owl")}]})
        require(write["position"] == "2", "Janus two-key update did not share one commit position")
        continuation = api(base, "/api/as-of-query", {**body, "cursor": first["next"], "limit": 1})
        require(continuation["rows"] == expected[1:] and continuation["position"] == "1",
                "Janus historical cursor drifted during a write")
        require(api(base, "/api/as-of-search", {"position": "1", "query": {
            "kind": "text", "key_prefix": key("text/"), "text": "quick fox"}, "limit": 8})["rows"] == text["rows"],
                "Janus historical text borrowed the updated value")
        require(api(base, "/api/search", {"kind": "text", "key_prefix": key("text/"), "text": "quick fox"})["rows"] == [],
                "Janus fixture current text did not change")
        scalar = api(base, "/api/as-of-search", {"position": "1", "query": {
            "kind": "json", "key_prefix": key("docs/"), "path": ["n"], "value": 1.0}, "limit": 8})
        require(scalar["rows"] == expected[1:], "Janus exact scalar search lost its original numeric encoding")
        require(api(base, "/api/as-of-get", {"position": "01", "key": key("docs/a")}, expected=400)["code"] == "nonexistent_position",
                "Janus malformed position error missing")
        require(api(base, "/api/as-of-get", {"position": "99", "key": key("docs/a")}, expected=400)["code"] == "future_position",
                "Janus future position error missing")
        api(base, "/api/checkpoint", {})
        require(api(base, "/api/as-of-query", body)["rows"] == expected, "Janus checkpoint changed retained results")
    with console(stage, db) as base:
        require(api(base, "/api/as-of-query", body)["rows"] == expected, "Janus reopen changed retained results")
        api(base, "/api/compact", {"position": "1"})
        require(api(base, "/api/as-of-query", body)["rows"] == expected, "Janus compaction changed retained floor result")
        api(base, "/api/compact", {"position": "2"})
        require(api(base, "/api/as-of-get", {"position": "1", "key": key("docs/a")}, expected=410)["code"] == "history_expired",
                "Janus cache silently extended the retention horizon")
    return ["0.9 historical point/range/typed JSON/text, explain, atomic snapshots, stable cursors, explicit position errors and checkpoint/compaction/reopen"]


def stdio_checks(stage, version):
    db = stage / "stdio-db"

    def exchange(requests):
        reply = subprocess.run([str(stage / "bin/polybase-stdio"), str(db)],
                               input="".join(json.dumps(request) + "\n" for request in requests),
                               capture_output=True, text=True, timeout=20)
        require(reply.returncode == 0, f"private-pipe runtime failed: {reply.stderr}")
        frames = [json.loads(line) for line in reply.stdout.splitlines()]
        require(len(frames) == len(requests) and all(frame.get("ok") is True for frame in frames),
                "private-pipe protocol rejected an acceptance frame")
        return [frame["result"] for frame in frames]

    frames = exchange([{"op": "info"}, {"op": "commit", "mutations": [
        {"key": "ledger/available", "value": "70"}, {"key": "ledger/reserved", "value": "30"}]},
        {"op": "scan", "after": None}, {"op": "close"}])
    require(frames[0]["version"] == version and frames[0]["protocol"] == 1,
            "private-pipe identity mismatch")
    expected = [["ledger/available", "70"], ["ledger/reserved", "30"]]
    require(frames[1]["head"] == frames[2]["head"] == "1" and frames[2]["rows"] == expected,
            "private-pipe batch/scan did not preserve atomic state")
    reopened = exchange([{"op": "info"}, {"op": "scan", "after": None}, {"op": "close"}])
    require(reopened[0]["head"] == "1" and reopened[1]["rows"] == expected,
            "private-pipe close/reopen changed state or retained the lock")
    return ["private-pipe embedding identity, atomic batch, ordered scan and immediate close/reopen"]


def runtime(stage, version):
    def run(binary, *args, success=True):
        reply = subprocess.run([str(stage / "bin" / binary), *map(str, args)], capture_output=True, text=True, timeout=20)
        require((reply.returncode == 0) == success, f"{binary} {args}: {reply.stderr}")
        return reply.stdout if success else reply.stderr
    for binary in BINS:
        require(version in run(binary, "--version"), "wrong runtime version")
        require("usage:" in run(binary, "--help"), "missing help")
    db = stage / "acceptance-db"
    require("head=0" in run("polybase", "init", db), "failed init")
    require("committed 1" in run("polybase", "batch", db, "put", "projects/a", "active", "put", "projects/b", "planned"), "failed batch")
    require(run("polybase", "get", db, "projects/a") == "active\n", "reopened value mismatch")
    require("next=1 head=1" in run("polybase", "events", db, 0, 10), "event mismatch")
    run("polybase", "batch", db, "put", "projects/a", "changed", "put", "incomplete", success=False)
    require(run("polybase", "get", db, "projects/a") == "active\n", "partial malformed batch applied")
    require("snapshot 1" in run("polybase", "snapshot", db), "wrong recovered prefix")
    console_evidence = console_checks(stage, db)
    collection_evidence = collection_checks(stage, run)
    cluster_evidence = cluster_checks(stage)
    preview7_evidence = preview7_checks(stage, run)
    preview82_evidence = preview82_checks(stage, run)
    stdio_evidence = stdio_checks(stage, version)
    janus_evidence = janus_checks(stage, run)
    damaged_db = stage / "damaged-db"
    run("polybase", "init", damaged_db)
    run("polybase", "put", damaged_db, "acknowledged", "value")
    wal = damaged_db / "wal"
    data = bytearray(wal.read_bytes())
    data[-1] ^= 1
    wal.write_bytes(data)
    damaged = wal.read_bytes()
    require("corruption" in run("polybase", "get", damaged_db, "acknowledged", success=False), "corruption did not fail closed")
    require(wal.read_bytes() == damaged, "corruption was silently rewritten")
    return ["all five binary identities/help", "atomic batch across independent reopens",
            "event/state prefix agreement", "malformed write has no partial effect",
            "protected WAL checksum corruption fails closed and is preserved", *console_evidence,
            *collection_evidence, *cluster_evidence, *preview7_evidence, *preview82_evidence, *stdio_evidence, *janus_evidence]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--runtime", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    manifest, contents, digest = verify(args.archive, args.expected_sha256, args.allow_dirty)
    checks = []
    if args.runtime:
        with tempfile.TemporaryDirectory(prefix="polybase-release-acceptance-") as temporary:
            stage = Path(temporary)
            for name, (data, mode) in contents.items():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(mode)
            checks = runtime(stage, manifest["version"])
    report = {"passed": True, "archive": args.archive.name, "sha256": digest,
              "source_commit": manifest["source_commit"], "source_dirty": manifest["source_dirty"],
              "target": manifest["target"], "files": len(contents), "dependencies": len(manifest["dependencies"]),
              "runtime_checks": checks}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
