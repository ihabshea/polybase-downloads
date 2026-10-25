#!/usr/bin/env python3
"""MIT-licensed Atlas QA SSH controller and agent; local fixtures never qualify.

Only the Python standard library is required. `self-test` tests the controller,
not a distributed database. See README.md for the trust and licensing boundaries.
Requires an explicitly provided public atlas-history-checker and separately
provided polybase-node artifacts. Contains no database/server implementation.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import errno
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import random
import re
import select
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zlib

PROTOCOL = 1
MAX_FRAME = 2 * 1024 * 1024
MAX_LINE = 32 * 1024 * 1024
MAX_VOLUME = 256 * 1024 * 1024
PROFILES = {"lan": 2, "wan": 40, "asymmetric": 12}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SHA = re.compile(r"[0-9a-f]{40,64}\Z")
NAME = re.compile(r"[a-zA-Z0-9_.-]{1,64}\Z")
HARNESS_ROOT = Path(__file__).resolve().parent
CHECKER_EXECUTABLE = None
CHECKER_SOURCE_SHA256 = "9b9e18dd96d112b531183815260e71434680fcdb74cb28566486a3b8cba31e7e"


def reject_constant(value):
    raise RuntimeError(f"nonfinite JSON constant: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def strict_json(value):
    return json.loads(value, object_pairs_hook=unique_object, parse_constant=reject_constant)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def bounded_json(path):
    path = Path(path)
    require(path.stat().st_size <= MAX_LINE, "JSON input exceeds 32 MiB")
    return strict_json(path.read_text())


def exact(stream, count):
    data = bytearray()
    while len(data) < count:
        block = stream.recv(count - len(data))
        require(block, "incomplete RPC frame")
        data.extend(block)
    return bytes(data)


def encode_frame(value):
    body = json.dumps(value, separators=(",", ":")).encode()
    require(0 < len(body) <= MAX_FRAME, "RPC payload exceeds bounded frame")
    return b"PBRPC001" + struct.pack("<II", len(body), zlib.crc32(body)) + body


def read_frame(stream):
    header = exact(stream, 16)
    require(header[:8] == b"PBRPC001", "unsupported RPC frame magic")
    size, crc = struct.unpack("<II", header[8:])
    require(0 < size <= MAX_FRAME, "RPC frame outside bounded length")
    body = exact(stream, size)
    require(zlib.crc32(body) == crc, "RPC frame checksum mismatch")
    return header + body, strict_json(body)


def address(text):
    host, port = text.rsplit(":", 1)
    ipaddress.IPv4Address(host)
    require(1 <= int(port) <= 65535, "invalid TCP port")
    return host, int(port)


def rpc(endpoint, command):
    with socket.create_connection(address(endpoint), timeout=5) as stream:
        stream.settimeout(6)
        stream.sendall(encode_frame({"kind": "client", "command": command}))
        _, reply = read_frame(stream)
    require(reply.get("kind") in {"ok", "error"}, "unsupported RPC response")
    return reply


def successful(reply):
    require(reply.get("kind") == "ok", f"RPC rejected: {reply}")
    return reply["value"]


class Journal:
    def __init__(self, path):
        self.path, self.lock = Path(path), threading.Lock()

    def emit(self, event, **fields):
        with self.lock:
            with self.path.open("a") as stream:
                stream.write(json.dumps({"event": event, "monotonic_ns": time.monotonic_ns(),
                                         "utc": now(), **fields}, sort_keys=True) + "\n")


def schedule(seed, ordinal, profile):
    """Decisions are fixed per directed-link ordinal, not PRNG call interleaving."""
    require(profile in PROFILES, "unknown network profile")
    rng = random.Random((seed << 20) ^ ordinal)
    links = {}
    for source in range(1, 4):
        for target in range(1, 4):
            if source == target:
                continue
            indices = rng.sample(range(2, 13), 4)
            links[f"{source}>{target}"] = {
                "base_delay_ms": PROFILES[profile] * (3 if profile == "asymmetric" and source > target else 1),
                "actions": {str(i): action for i, action in zip(indices, ["drop", "delay", "duplicate", "reorder"])},
                "delay_ms": rng.randrange(90, 170), "reorder_wait_ms": 1050,
            }
    return {"schema": 1, "seed": seed, "ordinal": ordinal, "profile": profile,
            "links": links, "workload_seed": rng.getrandbits(64),
            "transaction_kill_delay_ms": rng.randrange(0, 8),
            "phases": ["bootstrap", "network", "minority_partition", "majority_partition",
                       "leader_kill_during_transaction", "stale_return", "snapshot_disconnect",
                       "follower_enospc", "eventual_heal"],
            "schedule_determinism": "per-link receive ordinals and controller phase barriers; OS interleaving is measured, not replayed by assumption"}


class PeerProxy:
    """Bounded real TCP RPC impairment, never a database/client acknowledgment."""
    def __init__(self, source, target, listen, destination, journal):
        self.source, self.target = source, target
        self.destination, self.journal = destination, journal
        self.lock, self.stop = threading.Lock(), threading.Event()
        self.slots = threading.BoundedSemaphore(4)
        self.workers, self.pending = [], None
        self.rule, self.counter = {}, 0
        self.blocked = self.interrupt_install = False
        self.counts = {}
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(address(listen))
        self.listener.listen(4)
        self.listener.settimeout(0.2)
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def configure(self, rule, blocked=False, interrupt_install=False):
        with self.lock:
            self.rule, self.counter = rule, 0
            self.blocked, self.interrupt_install = blocked, interrupt_install
        self.journal.emit("link_configured", source=self.source, target=self.target,
                          rule=rule, blocked=blocked, interrupt_install=interrupt_install)

    def count(self, event, **fields):
        with self.lock:
            self.counts[event] = self.counts.get(event, 0) + 1
        self.journal.emit(event, source=self.source, target=self.target, **fields)

    def _accept(self):
        while not self.stop.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not self.slots.acquire(blocking=False):
                client.close()
                self.count("proxy_capacity_drop")
                continue
            self.workers = [worker for worker in self.workers if worker.is_alive()]
            worker = threading.Thread(target=self._receive, args=(client,), daemon=True)
            self.workers.append(worker)
            worker.start()

    def _forward(self, frame, ordinal, duplicate=False):
        with socket.create_connection(address(self.destination), timeout=2) as peer:
            peer.settimeout(5)
            peer.sendall(frame)
            response, reply = read_frame(peer)
        if reply.get("kind") == "error":
            self.count("peer_rejected", ordinal=ordinal, reply=reply)
            if "no space left" in str(reply).lower() or "os error 28" in str(reply).lower():
                self.count("peer_enospc", ordinal=ordinal, reply=reply)
        self.count("delivered", ordinal=ordinal, duplicate=duplicate,
                   frame_sha256=hashlib.sha256(frame).hexdigest(), bytes=len(frame))
        return response

    def _receive(self, client):
        held = None
        try:
            with client:
                client.settimeout(5)
                frame, packet = read_frame(client)
                require(packet.get("kind") == "atlas_peer" and packet.get("protocol") == 2,
                        "proxy accepts only protocol2 Atlas peer frames")
                message = packet["message"]
                require(message["from"] == self.source and message["to"] == self.target,
                        "peer frame is on the wrong directed link")
                with self.lock:
                    self.counter += 1
                    ordinal, rule, blocked = self.counter, dict(self.rule), self.blocked
                    interrupt = self.interrupt_install and message["body"]["kind"] == "install"
                action = "drop" if blocked else rule.get("actions", {}).get(str(ordinal), "deliver")
                self.count("received", ordinal=ordinal, action=action,
                           body_kind=message["body"]["kind"], frame_sha256=hashlib.sha256(frame).hexdigest())
                if action == "drop":
                    self.count("loss", ordinal=ordinal)
                    return
                if interrupt:
                    with self.lock:
                        self.interrupt_install = False
                    sent = max(17, len(frame) // 2)
                    with socket.create_connection(address(self.destination), timeout=2) as peer:
                        peer.sendall(frame[:sent])
                        peer.shutdown(socket.SHUT_WR)
                    self.count("snapshot_transfer_disconnected", ordinal=ordinal,
                               frame_bytes=len(frame), sent_bytes=sent,
                               frame_sha256=hashlib.sha256(frame).hexdigest())
                    return
                delay = rule.get("base_delay_ms", 0) + (rule.get("delay_ms", 0) if action == "delay" else 0)
                if delay:
                    start = time.monotonic_ns()
                    self.stop.wait(delay / 1000)
                    self.count("delay", ordinal=ordinal, requested_ms=delay,
                               actual_ns=time.monotonic_ns() - start)
                if action == "reorder":
                    held = threading.Event()
                    with self.lock:
                        require(self.pending is None, "only one bounded held frame is allowed")
                        self.pending = (held, ordinal)
                    if not held.wait(rule.get("reorder_wait_ms", 1050) / 1000):
                        self.count("reorder_expired_without_second_frame", ordinal=ordinal)
                    with self.lock:
                        if self.pending and self.pending[0] is held:
                            self.pending = None
                response = self._forward(frame, ordinal)
                with self.lock:
                    pending = self.pending if not held else None
                    if pending:
                        self.pending = None
                if pending:
                    self.count("reordered", first=pending[1], delivered_before=ordinal)
                    pending[0].set()
                if action == "duplicate":
                    self._forward(frame, ordinal, duplicate=True)
                    self.count("duplicate", ordinal=ordinal)
                client.sendall(response)
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            self.count("transport_error", error=str(error))
        finally:
            if held:
                with self.lock:
                    if self.pending and self.pending[0] is held:
                        self.pending = None
            self.slots.release()

    def close(self):
        self.stop.set()
        self.listener.close()
        with self.lock:
            if self.pending:
                self.pending[0].set()
        self.thread.join(timeout=2)
        for worker in self.workers:
            worker.join(timeout=7)
        require(not any(worker.is_alive() for worker in self.workers), "proxy worker did not stop")


def mount_evidence(path):
    path = Path(path).resolve(strict=True)
    rows = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        before, after = line.split(" - ", 1)
        fields, fs = before.split(), after.split()
        mount = fields[4].replace("\\040", " ")
        if path == Path(mount) or Path(mount) in path.parents:
            rows.append((len(mount), {"mountpoint": mount, "device": fields[2],
                                     "filesystem": fs[0], "source": fs[1]}))
    require(rows, "no mount evidence available")
    result = max(rows, key=lambda row: row[0])[1]
    stats = os.statvfs(path)
    return {**result, "path": str(path), "total_bytes": stats.f_blocks * stats.f_frsize,
            "available_bytes": stats.f_bavail * stats.f_frsize,
            "device_id": path.stat().st_dev}


def identity_hash(path):
    value = Path(path).read_text().strip()
    require(value, f"empty identity file: {path}")
    return hashlib.sha256(value.encode()).hexdigest()


class HostAgent:
    def __init__(self, enrollment):
        self.enrollment = bounded_json(enrollment)
        require(self.enrollment.get("schema") == 1, "unsupported enrollment schema")
        self.root = self.process = self.log_file = self.journal = self.filler = None
        self.proxies, self.tasks = {}, {}
        self.task_spans = {}
        self.task_pool = ThreadPoolExecutor(max_workers=2)
        self.task_counter = 0
        self.token = None
        self.completed = None

    def handshake(self):
        e = self.enrollment
        binary = Path(e["binary"]).resolve(strict=True)
        provenance = bounded_json(e["artifact_manifest"])
        require(provenance.get("binary_sha256") == digest(binary), "artifact manifest executable mismatch")
        require(SHA.fullmatch(provenance.get("source_sha", "")), "artifact manifest requires an operator-supplied source SHA label")
        version = subprocess.check_output([str(binary), "--version"], text=True, timeout=5).strip()
        require(provenance.get("schema") == 1 and provenance.get("engine_version") == version,
                "artifact manifest must record actual --version output")
        virtual = subprocess.run(["systemd-detect-virt"], capture_output=True, text=True, timeout=5).stdout.strip() if shutil.which("systemd-detect-virt") else "unknown"
        return {"agent_protocol": PROTOCOL, "agent_sha256": digest(__file__),
                "binary_sha256": digest(binary), "source_sha": provenance["source_sha"],
                "engine_source_provenance_verified": False,
                "source_label_trust": "unauthenticated operator-supplied artifact manifest claim",
                "artifact_manifest": provenance, "engine_version": version,
                "machine_id_sha256": identity_hash("/etc/machine-id"),
                "boot_id_sha256": identity_hash("/proc/sys/kernel/random/boot_id"),
                "uid": os.getuid(), "kernel": platform.release(), "architecture": platform.machine(),
                "hostname": socket.gethostname(), "virtualization": virtual,
                "container_marker": Path("/.dockerenv").exists() or Path("/run/.containerenv").exists(),
                "clock": {"utc": now(), "monotonic_ns": time.monotonic_ns(),
                          "resolution_seconds": time.get_clock_info("monotonic").resolution},
                "storage": mount_evidence(e["storage_mount"]),
                "scratch": mount_evidence(e["scratch_root"]),
                "dedicated_volume": e.get("dedicated_volume") is True,
                "node": e["node"], "allowed_peers": e["allowed_peers"], "proxy_ports": e["proxy_ports"],
                "independence_attestation": e.get("independence_attestation")}

    def _owned(self, request):
        require(self.root is not None and request.get("token") == self.token,
                "mutation requires this connection's owned run token")
        marker = bounded_json(self.root / "ownership.json")
        require(marker["token"] == self.token and marker["uid"] == os.getuid(), "run ownership mismatch")

    def _start(self):
        require(self.process is None or self.process.poll() is not None, "owned node is already alive")
        require(digest(self.enrollment["binary"]) == self.artifact_hashes["binary_sha256"]
                and digest(__file__) == self.artifact_hashes["agent_sha256"], "enrolled executable/agent changed during run")
        self.log_file = (self.root / "node.log").open("ab")
        command = [self.enrollment["binary"], str(self.root / "cluster.json"), str(self.node),
                   str(self.data), "--atlas-network", "--lab-controls"]
        self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                        stdout=self.log_file, stderr=subprocess.STDOUT)
        self.journal.emit("node_started", pid=self.process.pid, command=command)
        def listening():
            require(self.process.poll() is None, "owned node exited during start; never contact another process on its port")
            return self.owns_listener()
        wait_until(listening, seconds=10, description="listener inode owned by actual node child")
        return {"pid": self.process.pid}

    def owns_listener(self):
        if self.process is None or self.process.poll() is not None:
            return False
        host, port = address(self.endpoint)
        local = socket.inet_aton(host)[::-1].hex().upper() + f":{port:04X}"
        inodes = {fields[9] for fields in (line.split() for line in Path("/proc/net/tcp").read_text().splitlines()[1:])
                  if fields[1] == local and fields[3] == "0A"}
        sockets = {f"socket:[{inode}]" for inode in inodes}
        try:
            return any(os.readlink(fd) in sockets for fd in Path(f"/proc/{self.process.pid}/fd").iterdir())
        except (OSError, ProcessLookupError):
            return False

    def _kill(self):
        require(self.process is not None, "no owned child to terminate")
        pid = self.process.pid
        sent_ns = None
        if self.process.poll() is None:
            sent_ns = time.monotonic_ns()
            self.process.kill()
        code = self.process.wait(timeout=10)
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        self.journal.emit("node_terminated", pid=pid, returncode=code,
                          signal=-code if code < 0 else None, signal_sent_ns=sent_ns)
        return {"pid": pid, "returncode": code, "signal": -code if code < 0 else None, "signal_sent_ns": sent_ns}

    def prepare(self, request):
        require(self.root is None, "finish prior owned run before preparing another")
        require(self.completed is None, "export and release prior successful data, or preserve this failed session")
        e, config = self.enrollment, request["config"]
        require(NAME.fullmatch(request["run_id"]), "unsafe run identifier")
        require(request["node"] in {1, 2, 3}, "only three enrolled initial hosts are supported")
        require(request["node"] == e["node"], "requested node differs from enrolled node")
        require(config.get("transport") == "trusted_private" and config.get("genesis") == [1, 2, 3], "unsupported enrolled transport/genesis")
        enrolled_nodes = [{"id": int(node), "address": endpoint} for node, endpoint in sorted(e["allowed_peers"].items())]
        require(config["nodes"] == enrolled_nodes, "destinations differ from explicitly enrolled peer allowlist")
        own_routes = {str(route["to"]): address(route["address"])[1] for route in config["routes"] if route["from"] == e["node"]}
        require(own_routes == e["proxy_ports"], "proxy listeners differ from administrator enrollment")
        manifest = bounded_json(e["artifact_manifest"])
        require(request["source_sha"] == manifest["source_sha"], "requested source differs from enrolled artifact")
        self.artifact_hashes = {"binary_sha256": digest(e["binary"]), "agent_sha256": digest(__file__)}
        require(self.artifact_hashes["binary_sha256"] == manifest["binary_sha256"], "enrolled executable changed")
        storage = mount_evidence(e["storage_mount"])
        require(e.get("dedicated_volume") is True and storage["mountpoint"] == storage["path"],
                "dedicated operator-enrolled exact mountpoint required")
        require(0 < storage["total_bytes"] <= MAX_VOLUME, "dedicated fault volume must be at most 256 MiB")
        for path in [Path(e["storage_mount"]), Path(e["scratch_root"])]:
            require(path.stat().st_uid == os.getuid() and not path.is_symlink(), "scratch/mount must be owned by agent UID")
        self.root = Path(tempfile.mkdtemp(prefix=request["run_id"] + "-", dir=e["scratch_root"]))
        self.data = Path(tempfile.mkdtemp(prefix=request["run_id"] + "-", dir=e["storage_mount"]))
        self.token, self.node = os.urandom(24).hex(), request["node"]
        write_json(self.root / "ownership.json", {"token": self.token, "uid": os.getuid(), "data": str(self.data)})
        write_json(self.root / "cluster.json", config)
        self.journal = Journal(self.root / "agent.jsonl")
        journal = Journal(self.root / "proxy.jsonl")
        nodes = {n["id"]: n["address"] for n in config["nodes"]}
        self.endpoint = nodes[self.node]
        for route in config["routes"]:
            if route["from"] == self.node:
                require(address(route["address"])[0] == "127.0.0.1", "proxies bind loopback only")
                self.proxies[route["to"]] = PeerProxy(self.node, route["to"], route["address"], nodes[route["to"]], journal)
        require(len(self.proxies) == 2, "exactly two directed proxy routes required")
        self.journal.emit("prepared", data=str(self.data), source_sha=request["source_sha"])
        return {"token": self.token, "run_root": str(self.root), "data_root": str(self.data)}

    def _rpc(self, command, span=None):
        start = time.monotonic_ns()
        if span is not None:
            span["invocation_ns"] = start
        self.journal.emit("client_invoked", command=command, invocation_ns=start)
        try:
            require(self.owns_listener(), "owned node has no verified listener; refuse contacting an unrelated process")
            result = rpc(self.endpoint, command)
            self.journal.emit("client_completed", command=command, invocation_ns=start,
                              response_ns=time.monotonic_ns(), reply=result)
            return result
        except (OSError, RuntimeError, ValueError) as error:
            self.journal.emit("client_uncertain", command=command, invocation_ns=start,
                              response_ns=time.monotonic_ns(), error=str(error))
            return {"kind": "transport_uncertain", "message": str(error)}
        finally:
            if span is not None:
                span["response_ns"] = time.monotonic_ns()

    def handle(self, request):
        op = request["op"]
        if op == "handshake":
            return self.handshake()
        if op == "prepare":
            return self.prepare(request)
        if op == "release_data":
            return self.release_data(request)
        self._owned(request)
        if op == "start":
            return self._start()
        if op == "kill":
            if request.get("task"):
                require(request["task"] in self.tasks and not self.tasks[request["task"]].done(),
                        "client operation already completed before kill; cannot claim transaction overlap")
            return self._kill()
        if op == "rpc":
            return self._rpc(request["command"])
        if op == "rpc_async":
            require(len(self.tasks) < 2, "at most two outstanding client operations")
            self.task_counter += 1
            key = str(self.task_counter)
            self.task_spans[key] = {}
            self.tasks[key] = self.task_pool.submit(self._rpc, request["command"], self.task_spans[key])
            return {"task": key}
        if op == "rpc_result":
            future = self.tasks[request["task"]]
            result = future.result(timeout=10)
            del self.tasks[request["task"]]
            return {"reply": result, "agent_span": self.task_spans.pop(request["task"])}
        if op == "network":
            for target, proxy in self.proxies.items():
                proxy.configure(request.get("links", {}).get(f"{self.node}>{target}", {}),
                                target in request.get("blocked_targets", []),
                                target in request.get("interrupt_install_targets", []))
            return {"configured": True}
        if op == "metrics":
            return {str(target): dict(proxy.counts) for target, proxy in self.proxies.items()}
        if op == "fill_volume":
            require(self.filler is None, "volume already filled")
            evidence = mount_evidence(self.enrollment["storage_mount"])
            require(evidence["total_bytes"] <= MAX_VOLUME and self.enrollment["dedicated_volume"] is True,
                    "refuse filling an unenrolled or oversized filesystem")
            self.filler = self.data / "ATLAS_OWNED_ENOSPC_FILLER"
            written, observed = 0, None
            try:
                with self.filler.open("xb", buffering=0) as stream:
                    block = b"\0" * 65536
                    while written <= MAX_VOLUME:
                        count = stream.write(block)
                        require(count > 0, "fill write made no progress")
                        written += count
                    raise RuntimeError("bounded fill ended without ENOSPC")
            except OSError as error:
                require(error.errno == errno.ENOSPC, f"expected real ENOSPC, got errno {error.errno}")
                observed = error.errno
            self.journal.emit("volume_filled", written_bytes=written, errno=observed, filesystem=evidence)
            return {"written_bytes": written, "errno": observed, "real_enospc": observed == errno.ENOSPC}
        if op == "release_volume":
            if self.filler:
                self.filler.unlink(missing_ok=True)
                self.filler = None
            self.journal.emit("volume_released")
            return {"released": True}
        if op == "fault_status":
            tail = b""
            path = self.root / "node.log"
            if path.exists():
                with path.open("rb") as stream:
                    stream.seek(max(0, path.stat().st_size - 16384))
                    tail = stream.read()
            text = tail.decode(errors="replace")
            return {"returncode": self.process.poll() if self.process else None,
                    "log_observed_enospc": "no space left" in text.lower() or "os error 28" in text.lower(),
                    "node_log_tail": text}
        if op == "finish":
            return self.finish()
        raise RuntimeError("unknown agent operation")

    def finish(self):
        if self.process:
            self._kill()
        if self.filler:
            self.filler.unlink(missing_ok=True)
            self.filler = None
        for proxy in self.proxies.values():
            proxy.close()
        for future in self.tasks.values():
            future.result(timeout=10)
        self.tasks.clear()
        self.task_spans.clear()
        metrics = {str(target): dict(proxy.counts) for target, proxy in self.proxies.items()}
        files = {}
        total = 0
        for name in ["node.log", "agent.jsonl", "proxy.jsonl", "cluster.json", "ownership.json"]:
            path = self.root / name
            if path.exists():
                require(path.stat().st_size <= 12 * 1024 * 1024, "evidence file exceeds 12 MiB; remote files preserved")
                total += path.stat().st_size
                require(total <= 20 * 1024 * 1024, "evidence exceeds total export bound; remote files preserved")
                files[name] = base64.b64encode(path.read_bytes()).decode()
        manifest = [{"name": str(path.relative_to(self.data)), "bytes": path.stat().st_size,
                     "sha256": digest(path)} for path in sorted(self.data.rglob("*")) if path.is_file()]
        result = {"run_root": str(self.root), "data_root": str(self.data), "files": files,
                  "data_manifest": manifest, "metrics": metrics,
                  "remote_state_preserved": True, "release_token": self.token,
                  "artifact_final": {"binary_sha256": digest(self.enrollment["binary"]), "agent_sha256": digest(__file__)}}
        require(result["artifact_final"] == self.artifact_hashes, "remote executable/agent changed; preserve data and refuse qualification")
        self.completed = {"token": self.token, "root": self.root, "data": self.data}
        self.root = self.process = self.log_file = self.journal = self.token = None
        self.proxies = {}
        return result

    def release_data(self, request):
        completed = self.completed
        require(completed is not None and request.get("release_token") == completed["token"],
                "data release requires the exported completed run token")
        marker = bounded_json(completed["root"] / "ownership.json")
        require(marker["token"] == completed["token"] and marker["uid"] == os.getuid()
                and marker["data"] == str(completed["data"]), "completed run ownership mismatch")
        data = completed["data"]
        require(data.parent.resolve() == Path(self.enrollment["storage_mount"]).resolve()
                and not data.is_symlink(), "refuse deleting anything outside owned data root")
        shutil.rmtree(data)
        Journal(completed["root"] / "agent.jsonl").emit("owned_success_data_released_after_controller_export", data=str(data))
        self.completed = None
        return {"owned_data_released": True, "data_root": str(data), "scratch_evidence_retained": True}

    def close(self):
        if self.root:
            try:
                self.finish()
            except Exception as error:
                print(f"agent cleanup failed; owned state preserved: {error}", file=sys.stderr)
        self.task_pool.shutdown(wait=True)


def agent_main(args):
    agent = HostAgent(args.enrollment)
    try:
        while True:
            line = sys.stdin.buffer.readline(MAX_LINE + 1)
            if not line:
                break
            require(len(line) <= MAX_LINE, "agent input exceeds limit")
            request = strict_json(line)
            try:
                result = {"id": request["id"], "ok": True, "value": agent.handle(request)}
            except Exception as error:
                result = {"id": request.get("id"), "ok": False, "error": str(error)}
            print(json.dumps(result, separators=(",", ":")), flush=True)
    finally:
        agent.close()


def validate_inventory(inventory):
    require(inventory.get("schema") == 1, "unsupported inventory schema")
    require(inventory.get("transport") == "trusted_private", "explicit trusted_private transport enrollment required")
    hosts = inventory.get("hosts", [])
    require(len(hosts) == 3 and [h.get("node") for h in hosts] == [1, 2, 3], "exactly sorted initial nodes 1,2,3 required")
    require(SHA.fullmatch(inventory.get("source_sha", "")), "pin the operator-supplied artifact source SHA label")
    require(HEX64.fullmatch(inventory.get("binary_sha256", "")), "pin actual executable SHA256")
    require(HEX64.fullmatch(inventory.get("agent_sha256", "")), "pin actual agent SHA256")
    require(len(bytes.fromhex(inventory.get("partition", ""))) == 16
            and int(inventory["partition"], 16) != 0, "partition must be nonzero 16-byte hex")
    for host in hosts:
        require(NAME.fullmatch(host["name"]) and NAME.fullmatch(host["ssh_user"]), "unsafe host/user identifier")
        require(re.fullmatch(r"[a-zA-Z0-9_.:-]+", host["ssh_host"]) and not host["ssh_host"].startswith("-"), "unsafe SSH hostname")
        require(1 <= host.get("ssh_port", 22) <= 65535, "invalid SSH port")
        require(HEX64.fullmatch(host.get("machine_id_sha256", "")), "pin every enrolled machine identity")
        require(host.get("independent_host_or_vm") is True, "operator must attest independent hosts/VMs")
        require(host.get("independent_storage_network_clocks") is True, "operator must attest independent storage/network/clocks")
        require(Path(host["known_hosts"]).is_file(), "pinned known_hosts file must exist; never auto-accept keys")
        for name in ["agent_path", "enrollment_path"]:
            require(Path(host[name]).is_absolute(), "remote agent/enrollment paths must be absolute")
        ip = ipaddress.IPv4Address(host["peer_ip"])
        require(ip.is_private and not ip.is_loopback and not ip.is_link_local and not ip.is_unspecified,
                "peer must be an enrolled private IPv4 address")
        require(1 <= host["node_port"] <= 65535, "invalid node port")
        ports = [host["node_port"], *host["proxy_ports"].values()]
        require(len(ports) == 3 and len(set(ports)) == 3 and all(1 <= n <= 65535 for n in ports),
                "two proxy ports and node port must be distinct")
        require(set(host["proxy_ports"]) == {str(n) for n in [1, 2, 3] if n != host["node"]}, "proxy port map must cover the other two nodes")
    require(len({h["machine_id_sha256"] for h in hosts}) == 3, "duplicate enrolled machine identity")
    require(len({h["peer_ip"] for h in hosts}) == 3, "independent hosts need distinct peer IPs")


def validate_handshakes(inventory, handshakes):
    require(len(handshakes) == 3, "three completed read-only host handshakes required")
    boots, machines = set(), set()
    for host, value in zip(inventory["hosts"], handshakes):
        require(value["agent_protocol"] == PROTOCOL, "unsupported remote agent protocol")
        for field in ["agent_sha256", "binary_sha256", "source_sha"]:
            require(value[field] == inventory[field], f"{host['name']} {field} pin mismatch")
        require(value["machine_id_sha256"] == host["machine_id_sha256"], "machine identity does not match enrollment")
        require(value["node"] == host["node"] and value["proxy_ports"] == host["proxy_ports"], "remote endpoint enrollment differs from inventory")
        require(value["allowed_peers"] == {str(h["node"]): f"{h['peer_ip']}:{h['node_port']}" for h in inventory["hosts"]}, "remote peer allowlist differs from inventory")
        require(not value["container_marker"], "containers cannot qualify as independent hosts/VMs")
        require(value["virtualization"] in {"none", "kvm", "qemu", "vmware", "microsoft", "xen", "amazon", "oracle", "apple", "google"},
                "unrecognized/container virtualization cannot qualify; record administrator evidence")
        attestation = value.get("independence_attestation", {})
        require(all(attestation.get(k) is True for k in ["storage", "network", "clocks"]), "remote independent storage/network/clocks attestation missing")
        require(attestation.get("kind") in {"physical_host", "isolated_vm"} and attestation.get("evidence"), "remote host/VM evidence required")
        volume = value["storage"]
        require(value["dedicated_volume"] and volume["mountpoint"] == volume["path"]
                and 0 < volume["total_bytes"] <= MAX_VOLUME, "real ENOSPC requires dedicated bounded mount")
        require(volume["filesystem"] in {"ext4", "xfs", "btrfs"}, "qualification storage must be a durable dedicated filesystem")
        require(value["scratch"]["device_id"] != volume["device_id"], "fault volume must not contain agent/evidence scratch")
        machines.add(value["machine_id_sha256"])
        boots.add(value["boot_id_sha256"])
    require(len(machines) == len(boots) == 3, "three unique machine AND kernel boot identities required")


def cluster_config(inventory):
    return {"partition": inventory["partition"], "genesis": [1, 2, 3],
            "transport": "trusted_private",
            "nodes": [{"id": h["node"], "address": f"{h['peer_ip']}:{h['node_port']}"} for h in inventory["hosts"]],
            "routes": [{"from": h["node"], "to": int(target), "address": f"127.0.0.1:{port}"}
                       for h in inventory["hosts"] for target, port in sorted(h["proxy_ports"].items())]}


class Remote:
    def __init__(self, host, directory):
        self.host, self.serial, self.token = host, 0, None
        self.journal = Journal(directory / f"ssh-{host['name']}.jsonl")
        command = ["ssh", "-F", "/dev/null", "-T", "-p", str(host.get("ssh_port", 22)),
                   "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                   "-o", "UserKnownHostsFile=" + str(Path(host["known_hosts"]).resolve()),
                   "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1",
                   "-o", "ForwardAgent=no", "-o", "ClearAllForwardings=yes",
                   "-o", "PermitLocalCommand=no", "-o", "ServerAliveInterval=5",
                   "-o", "ServerAliveCountMax=2", "-o", "LogLevel=ERROR",
                   f"{host['ssh_user']}@{host['ssh_host']}",
                   shlex.join(["python3", host["agent_path"], "agent", "--enrollment", host["enrollment_path"]])]
        self.stderr = (directory / f"ssh-{host['name']}.stderr.log").open("ab")
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.stderr, bufsize=0)
        self.buffer = bytearray()
        self.journal.emit("ssh_started", command=command, pid=self.process.pid)

    def request(self, op, timeout=30, **fields):
        self.serial += 1
        request = {"id": self.serial, "op": op, **fields}
        if self.token:
            request["token"] = self.token
        invoked = time.monotonic_ns()
        self.journal.emit("invocation", request=request, invocation_ns=invoked)
        self.process.stdin.write(json.dumps(request, separators=(",", ":")).encode() + b"\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            require(remaining > 0, f"SSH agent response timeout on {self.host['name']} op={op}")
            readable, _, _ = select.select([self.process.stdout], [], [], min(remaining, 1))
            if readable:
                block = os.read(self.process.stdout.fileno(), 65536)
                require(block, f"SSH agent disconnected on {self.host['name']}")
                self.buffer.extend(block)
                require(len(self.buffer) <= MAX_LINE, "remote response exceeds bounded line")
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        result = strict_json(line)
        self.journal.emit("response", request_id=self.serial, invocation_ns=invoked,
                          response_ns=time.monotonic_ns(), result=result)
        require(result.get("id") == self.serial, "agent response identity mismatch")
        require(result.get("ok") is True, f"agent {self.host['name']} rejected {op}: {result.get('error')}")
        if op == "prepare":
            self.token = result["value"]["token"]
        if op == "finish":
            self.token = None
        return result["value"]

    def close(self):
        try:
            self.process.stdin.close()
            self.process.wait(timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            self.process.kill()
            self.process.wait(timeout=5)
        self.stderr.close()


def wait_until(condition, seconds=35, description="eventual condition"):
    deadline = time.monotonic() + seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = condition()
            if result:
                return result
        except (OSError, RuntimeError) as error:
            last_error = str(error)
        time.sleep(0.1)
    raise RuntimeError(f"deadline waiting for {description}; last error={last_error}")


class Scenario:
    def __init__(self, inventory, remotes, plan, directory, engine_version):
        self.inventory, self.remotes, self.plan, self.directory = inventory, remotes, plan, directory
        self.model, self.pending, self.calls = {}, [], []
        self.alive, self.last_leader = set(), None
        self.rng = random.Random(plan["workload_seed"])
        self.serial = 0
        self.events = Journal(directory / "controller.jsonl")
        self.coverage = {}
        self.engine_version = engine_version
        self.receipts, self.checker_segments, self.checked_call_cursor = {}, [], 0
        self.applied_anchor = None
        self.checker_initial = {"position": {"index": 0, "term": 0}, "rows": [], "requests": []}

    def mark(self, name, **evidence):
        self.coverage[name] = self.coverage.get(name, 0) + 1
        self.events.emit(name, **evidence)

    def call(self, node, command):
        invocation = time.monotonic_ns()
        result = self.remotes[node - 1].request("rpc", command=command)
        record = {"node": node, "command": command, "invocation_ns": invocation,
                  "response_ns": time.monotonic_ns(), "reply": result}
        self.calls.append(record)
        self.events.emit("client_observation", **record)
        return result

    def leader(self, exclude=()):
        def find():
            for node in sorted(self.alive - set(exclude)):
                result = self.call(node, {"op": "status"})
                if result.get("kind") == "ok" and result["value"].get("role") == "leader":
                    # A local role is insufficient; require an actual quorum barrier.
                    barrier = self.call(node, {"op": "snapshot", "query": {"key_prefix": "", "predicate": "any", "value": ""}, "mode": "quorum", "minimum": None})
                    if barrier.get("kind") == "ok":
                        self.last_leader = node
                        self.last_quorum_snapshot = barrier["value"]
                        return node
        return wait_until(find, description="leader with successful quorum barrier")

    def network(self, links=None, blocked=(), interrupt_target=None):
        for node, remote in enumerate(self.remotes, 1):
            remote.request("network", links=links or {},
                           blocked_targets=[target for source, target in blocked if source == node],
                           interrupt_install_targets=[] if interrupt_target is None or node == interrupt_target else [interrupt_target])

    def new_write(self, node, value_bytes=80):
        self.serial += 1
        # Distinct transaction keys keep ambiguous outcomes independent of later intents.
        value = (f"atlas/{self.plan['seed']}/{self.serial}/".encode() + self.rng.randbytes(value_bytes)).hex()
        keys = [f"tx/{self.serial:04}/{part}".encode().hex() for part in ["a", "b"]]
        intent = {"reads": [{"key": k, "value": None} for k in keys],
                  "mutations": [{"key": k, "value": value} for k in keys]}
        token = successful(self.call(node, {"op": "issue"}))["request_token"]
        return {"token": token, "intent": intent}

    def account(self, write, reply):
        if reply.get("kind") == "ok":
            value = reply["value"]
            if value.get("status") in {"applied", "conflict"}:
                require(value.get("durable") is True, "terminal response did not advertise durability")
                self.receipts[write["token"]] = {"request_id": canonical_token(write["token"]),
                                                "intent": checker_intent(write["intent"]),
                                                "position": checker_position(value), "status": value["status"]}
                if value["status"] == "applied":
                    for mutation in write["intent"]["mutations"]:
                        self.model[mutation["key"]] = mutation["value"]
                    self.applied_anchor = (write, value)
                return True
            raise RuntimeError(f"unexpected nonterminal write result: {value}")
        self.pending.append(write)
        self.events.emit("uncertain_write", write=write, observation=reply,
                         note="transport timeout/error is not a definite abort")
        return False

    def write(self, value_bytes=80):
        node = self.leader()
        write = self.new_write(node, value_bytes)
        reply = self.call(node, {"op": "write", **write})
        self.account(write, reply)
        return write, reply

    def reconcile(self):
        while self.pending:
            write = self.pending[0]
            for _ in range(8):
                node = self.leader()
                reply = self.call(node, {"op": "outcome", **write})
                if reply.get("kind") == "ok" and reply["value"].get("status") == "absent":
                    # Absence does not cancel an uncertain proposal. Resolve the
                    # same identity before cutting the checker history.
                    reply = self.call(node, {"op": "write", **write})
                if reply.get("kind") == "ok" and reply["value"].get("status") in {"applied", "conflict"}:
                    self.account(write, reply)
                    self.pending.pop(0)
                    self.mark("uncertain_outcome_resolved", write=write, reply=reply)
                    break
            else:
                raise RuntimeError("uncertain write lacks terminal retained receipt after bounded exact-identity retries")

    def check(self):
        self.reconcile()
        expected = sorted(self.model.items(), key=lambda row: bytes.fromhex(row[0]))
        for node in sorted(self.alive):
            def converged():
                reply = self.call(node, {"op": "snapshot", "query": {"key_prefix": "", "predicate": "any", "value": ""}, "mode": "local", "minimum": None})
                if reply.get("kind") != "ok":
                    return False
                rows = [(row["key"], row["value"]) for row in reply["value"]["rows"]]
                require(len({k for k, _ in rows}) == len(rows), "duplicate snapshot rows")
                require(rows == sorted(rows, key=lambda row: bytes.fromhex(row[0])), "snapshot byte-key ordering violation")
                require(all(k in self.model and self.model[k] == v for k, v in rows), "invented or incorrect visible record")
                # Each two-key transaction must be present atomically, even on a stale follower.
                present = {k for k, _ in rows}
                for key in self.model:
                    mate = (bytes.fromhex(key)[:-1] + (b"b" if bytes.fromhex(key)[-1:] == b"a" else b"a")).hex()
                    require((key in present) == (mate in present), "partial two-key transaction visible")
                return rows == expected
            wait_until(converged, description=f"exact reference convergence on node {node}")
        self.mark("reference_state_parity", keys=len(expected))
        # End a bounded checker segment only after every ambiguous write resolves,
        # all local snapshots converge, and an actual quorum snapshot confirms it.
        self.leader()
        boundary = self.last_quorum_snapshot
        require([(r["key"], r["value"]) for r in boundary["rows"]] == expected,
                "quorum snapshot disagrees with reference at checker segment boundary")
        self.checker_segments.append(self.checker_history(self.calls[self.checked_call_cursor:]))
        self.checked_call_cursor = len(self.calls)
        self.checker_initial = {"position": checker_position(boundary),
                                "rows": [[list(bytes.fromhex(k)), list(bytes.fromhex(v))] for k, v in expected],
                                "requests": list(self.receipts.values())}

    def checker_history(self, calls):
        operations = checker_operations(calls)
        require(len(operations) <= 64, "independent checker segment exceeds 64-operation bound; cannot qualify")
        return {"schema": 1, "engine_version": self.engine_version, "seed": self.plan["seed"],
                "history_id": self.plan["ordinal"] * 1000 + len(self.checker_segments),
                "profile": self.plan["profile"], "cluster_id": self.inventory["partition"],
                "membership_generation": 0, "failure_point": None,
                "replay_command": "python3 atlas-cross-host.py run --replay-schedule schedule.json --inventory INVENTORY --checker-binary PUBLIC_CHECKER --output NEW_OUTPUT",
                "initial": self.checker_initial, "operations": operations}

    def kill(self, node, require_sigkill=True, task=None):
        result = self.remotes[node - 1].request("kill", task=task)
        require(not require_sigkill or result["signal"] == signal.SIGKILL, "termination did not observe actual SIGKILL")
        self.alive.discard(node)
        self.mark("actual_sigkill" if result["signal"] == signal.SIGKILL else "observed_node_exit", node=node, result=result)
        return result

    def start(self, node):
        self.remotes[node - 1].request("start")
        self.alive.add(node)
        def ready():
            hello = self.call(node, {"op": "hello"})
            if hello.get("kind") != "ok":
                return False
            value = hello["value"]
            require(value.get("protocol") == 2 and value.get("transport") == "trusted_private",
                    "runtime did not negotiate Atlas protocol2 trusted_private transport")
            require("named-retries-v1" in value.get("capabilities", []), "named retry capability absent")
            require(value.get("partition") == self.inventory["partition"] and value.get("node") == node
                    and value.get("genesis") == [1, 2, 3], "hello returned another cluster/node identity")
            return True
        wait_until(ready, description=f"Atlas hello node {node}")

    def execute(self):
        config = cluster_config(self.inventory)
        for node, remote in enumerate(self.remotes, 1):
            result = remote.request("prepare", run_id=f"atlas-{self.plan['ordinal']:05}-{self.plan['seed']}",
                                    config=config, node=node, source_sha=self.inventory["source_sha"])
            self.events.emit("remote_prepared", node=node, **result)
        for node in range(1, 4):
            self.start(node)
        for _ in range(3):
            self.write()
        self.check()
        self.network(self.plan["links"])
        for _ in range(4):
            self.write()
        self.network()
        self.check()

        # Minority leader loses bidirectional contact. A timeout may still commit.
        stale = self.leader()
        attempt = self.new_write(stale)
        blocked = [(a, b) for a in range(1, 4) for b in range(1, 4) if a != b and (a == stale or b == stale)]
        self.network(blocked=blocked)
        self.account(attempt, self.call(stale, {"op": "write", **attempt}))
        replacement = self.leader(exclude=[stale])
        self.mark("minority_partition", stale_leader=stale, majority_leader=replacement, blocked=blocked)
        self.write()

        # All three separated: no quorum may return a durable applied result.
        isolated_attempt = self.new_write(replacement)
        all_links = [(a, b) for a in range(1, 4) for b in range(1, 4) if a != b]
        self.network(blocked=all_links)
        isolated_reply = self.call(replacement, {"op": "write", **isolated_attempt})
        require(not (isolated_reply.get("kind") == "ok" and isolated_reply["value"].get("status") == "applied"),
                "acknowledged write while every voter link was blocked")
        self.account(isolated_attempt, isolated_reply)
        self.mark("majority_partition", blocked=all_links, reply=isolated_reply)
        self.network()
        self.check()
        self.mark("stale_leader_returned", node=stale)

        # Overlap a real outstanding client call with an observed process kill.
        node = self.leader()
        attempt = self.new_write(node)
        require(self.applied_anchor is not None, "no acknowledged transaction available for leader-change retry")
        anchor, anchor_receipt = self.applied_anchor
        self.network(links={f"{node}>{other}": {"base_delay_ms": 1100} for other in range(1, 4) if other != node})
        invocation = time.monotonic_ns()
        task = self.remotes[node - 1].request("rpc_async", command={"op": "write", **attempt})["task"]
        time.sleep(self.plan["transaction_kill_delay_ms"] / 1000)
        killed = self.kill(node, task=task)
        completed = self.remotes[node - 1].request("rpc_result", task=task)
        reply, span = completed["reply"], completed["agent_span"]
        require(span["invocation_ns"] <= killed["signal_sent_ns"] < span["response_ns"],
                "SIGKILL did not overlap actual agent client operation; cannot count transaction termination")
        self.calls.append({"node": node, "command": {"op": "write", **attempt}, "invocation_ns": invocation,
                           "response_ns": time.monotonic_ns(), "reply": reply})
        self.account(attempt, reply)
        self.mark("leader_kill_during_transaction", node=node, signal_sent_ns=killed["signal_sent_ns"], actual_agent_span=span)
        self.network()
        self.leader()
        self.start(node)
        self.check()
        # Retrying a definite or resolved applied write must preserve its outcome.
        retry_node = self.leader()
        prior = successful(self.call(retry_node, {"op": "outcome", **anchor}))
        replay = successful(self.call(retry_node, {"op": "write", **anchor}))
        require(replay.get("replayed") is True and all(replay.get(k) == prior.get(k) == anchor_receipt.get(k) for k in ["position", "term", "status"]), "acknowledged named retry outcome changed after leadership transition")
        self.mark("named_retry_preserved", original=anchor_receipt, outcome=prior, retry=replay)

        # A sufficiently stale follower must use an actual Install transfer.
        leader = self.leader()
        follower = next(n for n in sorted(self.alive) if n != leader)
        self.kill(follower)
        for _ in range(8):
            self.write(value_bytes=4096)
        leader = self.leader()
        successful(self.call(leader, {"op": "compact"}))
        self.network(interrupt_target=follower)
        self.start(follower)
        def disconnected():
            return sum(counts.get("snapshot_transfer_disconnected", 0)
                       for remote in self.remotes for counts in remote.request("metrics").values()) > 0
        wait_until(disconnected, description="observed partial Install TCP transfer disconnection")
        self.mark("snapshot_transfer_disconnected", follower=follower,
                  boundary="partial incoming RPC frame; not a durable-install process failpoint")
        self.network()
        self.check()

        leader = self.leader()
        follower = next(n for n in sorted(self.alive) if n != leader)
        fill = self.remotes[follower - 1].request("fill_volume", timeout=30)
        require(fill.get("real_enospc") is True, "no real disk-full evidence")
        self.write()
        def engine_enospc():
            fault = self.remotes[follower - 1].request("fault_status")
            counts = sum(c.get("peer_enospc", 0) for remote in self.remotes for c in remote.request("metrics").values())
            return fault if fault["log_observed_enospc"] or counts > 0 else None
        io_evidence = wait_until(engine_enospc, description="actual follower persistence ENOSPC, not only a full filesystem")
        self.kill(follower, require_sigkill=False)
        self.remotes[follower - 1].request("release_volume")
        self.start(follower)
        self.check()
        self.mark("follower_disk_full_restart", node=follower, fill=fill, engine_io_evidence=io_evidence)
        self.mark("eventual_connectivity_reference_parity")
        return {"coverage": self.coverage, "reference_rows": [{"key": k, "value": v} for k, v in sorted(self.model.items())],
                "calls": self.calls, "unresolved_outcomes": len(self.pending),
                "note": "All supported wire observations are also submitted to the independent checker in reference-linked bounded segments."}


def canonical_token(token):
    result = bytes.fromhex(token).hex()
    require(result and result == token.lower(), "malformed request identity")
    return result


def checker_position(value):
    # Exact committed log index/term from the wire, never a local Engine position.
    return {"index": int(value["position"]), "term": int(value["term"])}


def checker_intent(intent):
    return {"expected": [{"key": list(bytes.fromhex(r["key"])),
                          "value": None if r["value"] is None else list(bytes.fromhex(r["value"]))}
                         for r in intent["reads"]],
            "mutations": [{"mutation": "delete", "key": list(bytes.fromhex(m["key"]))} if m["value"] is None
                          else {"mutation": "put", "key": list(bytes.fromhex(m["key"])), "value": list(bytes.fromhex(m["value"]))}
                          for m in intent["mutations"]]}


def checker_operations(calls):
    result = []
    for observed in calls:
        command, reply = observed["command"], observed["reply"]
        op = command["op"]
        if op not in {"write", "snapshot", "outcome"}:
            continue  # Retain all administrative observations in the raw transcript.
        if op == "snapshot":
            query = command["query"]
            require(query["predicate"] == "any" and query["value"] == "", "checker cannot discard an unsupported value filter")
            call = {"call": "read", "mode": command["mode"], "minimum": command["minimum"],
                    "query": {"query": "prefix", "prefix": list(bytes.fromhex(query["key_prefix"]))}}
        else:
            call = {"call": op, "request_id": canonical_token(command["token"]),
                    "intent": None if command.get("intent") is None else checker_intent(command["intent"])}
        if reply.get("kind") == "ok":
            value = reply["value"]
            if op == "snapshot":
                require(value.get("mode") == command["mode"], "snapshot consistency mode changed")
                outcome = {"outcome": "snapshot", "position": checker_position(value),
                           "rows": [[list(bytes.fromhex(row["key"])), list(bytes.fromhex(row["value"]))] for row in value["rows"]]}
            elif value.get("status") == "absent" and op == "outcome":
                outcome = {"outcome": "absent"}
            else:
                require(value.get("status") in {"applied", "conflict"}, "receipt status is outside independent checker model")
                require(value.get("durable") is True and type(value.get("wrote")) is bool
                        and value["wrote"] == (value["status"] == "applied"), "receipt durability/wrote flags contradict checker model")
                require(type(value.get("replayed")) is bool, "receipt lacks actual replay flag")
                outcome = {"outcome": "receipt", "position": checker_position(value),
                           "status": value["status"], "replayed": value["replayed"]}
        elif reply.get("kind") == "error" and op == "write" and reply.get("code") == "request_mismatch":
            outcome = {"outcome": "request_mismatch"}
        elif reply.get("kind") == "error" and op == "write" and reply.get("code") in {"not_leader", "invalid_request", "request_expired", "capacity"}:
            outcome = {"outcome": "definitive_abort", "reason": json.dumps(reply, sort_keys=True)}
        else:
            outcome = {"outcome": "unknown", "reason": json.dumps(reply, sort_keys=True)}
        result.append({"id": len(result) + 1, "client": observed["node"], "node": observed["node"],
                       "invocation": observed["invocation_ns"], "response": observed["response_ns"],
                       "call": call, "outcome": outcome})
    return result


def run_independent_checker(scenario, executable, directory):
    histories = list(scenario.checker_segments)
    tail = scenario.calls[scenario.checked_call_cursor:]
    if checker_operations(tail):
        histories.append(scenario.checker_history(tail))
    require(histories, "no checker histories captured")
    results = []
    for ordinal, history in enumerate(histories):
        path = directory / f"checker-history-{ordinal:02}.jsonl"
        payload = json.dumps(history, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        require(len(payload) <= 16 * 1024 * 1024, "public checker input exceeds 16 MiB line limit")
        path.write_bytes(payload)
        command = [str(executable)]
        checked = subprocess.run(command, input=payload, capture_output=True, timeout=90)
        require(len(checked.stdout) <= MAX_LINE and len(checked.stderr) <= 65536, "public checker output exceeds evidence bounds")
        (directory / f"checker-{ordinal:02}.stdout.log").write_bytes(checked.stdout)
        (directory / f"checker-{ordinal:02}.stderr.log").write_bytes(checked.stderr)
        stdout = checked.stdout.decode()
        lines = stdout.splitlines()
        require(len(lines) == 2, "public checker must emit one record and one final summary")
        record, summary = [strict_json(line) for line in lines]
        require(record.get("schema") == summary.get("schema") == 1
                and record.get("type") == "record" and summary.get("type") == "summary",
                "unsupported public checker response schema")
        require(record.get("engine_executed") is False and summary.get("engine_executed") is False,
                "recorded-observation checker must not claim engine execution")
        require(record.get("checker_source_sha256") == summary.get("checker_source_sha256") == CHECKER_SOURCE_SHA256,
                "public checker source identity mismatch")
        require(record.get("line") == 1 and record.get("history_id") == history["history_id"]
                and record.get("seed") == history["seed"] and summary.get("records") == 1,
                "public checker response does not bind exact submitted history")
        result = record["result"]
        results.append({"command": command, "input_file": path.name,
                        "input_sha256": hashlib.sha256(payload).hexdigest(),
                        "returncode": checked.returncode, "result": result,
                        "record": record, "summary": summary})
        write_json(directory / "independent-checker.json", results)
        require(checked.returncode == 0 and result.get("status") == "linearizable"
                and record.get("passed") is True and summary.get("all_passed") is True
                and summary.get("linearizable") == 1 and summary.get("violations") == 0
                and summary.get("inconclusive") == 0 and summary.get("invalid") == 0
                and summary.get("input_stopped_at_limit") is False,
                f"independent checker did not establish linearizability: {result}")
    return {"histories_checked": len(results), "operations_checked": sum(len(h["operations"]) for h in histories),
            "all_supported_observations_checked": True, "results": results,
            "segmentation": "reference-linked segments end after resolved outcomes and exact all-node convergence plus quorum snapshot; all supported observations remain present"}


def export_evidence(directory, node, evidence):
    destination = directory / f"node-{node}"
    destination.mkdir()
    files = evidence.pop("files")
    require(set(files) <= {"node.log", "agent.jsonl", "proxy.jsonl", "cluster.json", "ownership.json"}, "unexpected evidence file")
    for name, encoded in files.items():
        (destination / name).write_bytes(base64.b64decode(encoded, validate=True))
    write_json(destination / "remote-state.json", evidence)
    return evidence


def harness_state():
    # Works from a detached public QA bundle without Git or engine source. A
    # node's source label is a separate, unauthenticated operator assertion.
    tree = hashlib.sha256()
    paths = [Path(__file__).resolve(), HARNESS_ROOT / "cluster_driver.py", HARNESS_ROOT / "LICENSE",
             *sorted((HARNESS_ROOT / "examples").glob("*.example.json"))]
    files = {}
    for path in paths:
        require(path.is_file(), f"public QA bundle file missing: {path.name}")
        name = str(path.relative_to(HARNESS_ROOT))
        files[name] = digest(path)
        tree.update(name.encode() + b"\0" + path.read_bytes())
    return {"controller_sha256": digest(__file__), "qa_tree_sha256": tree.hexdigest(),
            "qa_file_sha256": files, "engine_source_provenance_verified": False,
            "engine_source_label_trust": "unauthenticated operator-supplied artifact manifest claim"}


def campaign(args):
    inventory = bounded_json(args.inventory)
    validate_inventory(inventory)
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    require(not any(directory.iterdir()), "output directory must be empty; preserve prior evidence")
    write_json(directory / "inventory.json", inventory)
    before = harness_state()
    report = {"schema": 1, "started_utc": now(), "source": before,
              "controller_protocol": PROTOCOL, "qualification_requested": getattr(args, "qualify", False),
              "cross_host_campaign_passed": False, "release_qualified": False,
              "schedules_planned": 0, "schedules_executed": 0, "schedules_passed": 0,
              "host_handshakes_verified": False, "profiles_executed": [],
              "engine_source_provenance_verified": False,
              "engine_source_label": inventory["source_sha"],
              "engine_source_label_trust": "unauthenticated operator-supplied artifact manifest claim",
              "measured_fault_counts": {},
              "scope": "three enrolled independent hosts/VMs; actual peer TCP frames and child processes",
              "non_claims": ["not a proof of all schedules", "not a host-power-loss test",
                             "CRC is not authenticated transport", "does not replace the independent cluster checker",
                             "does not qualify membership, rolling upgrades, historical-query or performance gates"]}
    remotes = []
    try:
        if args.command == "run":
            args.checker = args.checker.resolve(strict=True)
            report["checker"] = {"executable": str(args.checker), "sha256": digest(args.checker),
                                  "interface": "public atlas-history-checker NDJSON History stdin + EOF summary",
                                  "expected_checker_source_sha256": CHECKER_SOURCE_SHA256}
        if getattr(args, "qualify", False):
            require(args.schedules >= 10000 and set(args.profiles) == set(PROFILES), "qualification requires at least 10,000 schedules across all three profiles")
        for host in inventory["hosts"]:
            remotes.append(Remote(host, directory))
        handshakes = [remote.request("handshake") for remote in remotes]
        write_json(directory / "host-handshakes.json", handshakes)
        validate_handshakes(inventory, handshakes)
        report["host_handshakes_verified"] = True
        if args.command == "inspect":
            report["inspection_passed"] = True
            return
        if getattr(args, "replay_schedule", None):
            plans = [bounded_json(args.replay_schedule)]
            replay = plans[0]
            require(replay.get("schema") == 1 and replay.get("profile") in PROFILES
                    and type(replay.get("seed")) is int and 0 <= replay["seed"] < 2**64
                    and type(replay.get("ordinal")) is int and 0 <= replay["ordinal"] < 100000,
                    "unsupported or out-of-bounds replay schedule")
            require(replay == schedule(replay["seed"], replay["ordinal"], replay["profile"]),
                    "replay schedule differs from its recorded deterministic configuration")
        else:
            plans = (schedule(args.seed, i, args.profiles[i % len(args.profiles)]) for i in range(args.schedules))
        report["schedules_planned"] = 1 if getattr(args, "replay_schedule", None) else args.schedules
        total_counts, profiles = {}, set()
        for plan in plans:
            case = directory / f"schedule-{plan['ordinal']:05}"
            case.mkdir()
            write_json(case / "schedule.json", plan)
            result = {"schema": 1, "started_utc": now(), "passed": False, "seed": plan["seed"],
                      "ordinal": plan["ordinal"], "profile": plan["profile"],
                      "source_sha": inventory["source_sha"], "binary_sha256": inventory["binary_sha256"],
                      "actual_cross_host_execution": True, "host_identity_evidence": "../host-handshakes.json"}
            scenario = Scenario(inventory, remotes, plan, case, handshakes[0]["engine_version"])
            report["schedules_executed"] += 1
            error = None
            try:
                result.update(scenario.execute())
                result["independent_checker"] = run_independent_checker(scenario, args.checker, case)
                result["passed"] = True
            except Exception as failure:
                error = str(failure)
                result.update({"error": error, "coverage": scenario.coverage, "calls": scenario.calls,
                               "unresolved_outcomes": len(scenario.pending),
                               "replay_command": shlex.join(["python3", str(Path(__file__).resolve()), "run", "--inventory", str(args.inventory.resolve()),
                                                             "--checker-binary", str(args.checker), "--replay-schedule", str((case / "schedule.json").resolve()), "--output", str(directory) + "-replay"]),
                               "replay_limit": "same decisions and workload; OS scheduling and consensus event order must be remeasured"})
            finally:
                for node, remote in enumerate(remotes, 1):
                    if not remote.token:
                        continue
                    try:
                        evidence = remote.request("finish", timeout=60)
                        evidence = export_evidence(case, node, evidence)
                        if error is None:
                            released = remote.request("release_data", release_token=evidence["release_token"])
                            evidence["remote_state_preserved"] = False
                            evidence["data_release"] = released
                            write_json(case / f"node-{node}" / "remote-state.json", evidence)
                        for counts in evidence["metrics"].values():
                            for name, count in counts.items():
                                total_counts[name] = total_counts.get(name, 0) + count
                    except Exception as failure:
                        result["passed"] = False
                        result.setdefault("evidence_errors", []).append({"node": node, "error": str(failure)})
                result["finished_utc"] = now()
                write_json(case / "result.json", result)
            profiles.add(plan["profile"])
            report["profiles_executed"] = sorted(profiles)
            report["measured_fault_counts"] = total_counts
            if result["passed"]:
                report["schedules_passed"] += 1
            write_json(directory / "report.json", report)
            require(result["passed"], f"schedule {plan['ordinal']} failed: {error}; evidence preserved in {case}")
        after = harness_state()
        report["source_after"] = after
        require(before == after, "public QA controller/bundle changed during campaign; cannot qualify")
        if args.qualify:
            require(all(total_counts.get(name, 0) > 0 for name in ["loss", "delay", "duplicate", "reordered", "snapshot_transfer_disconnected"]), "declared fault type lacks observed delivery evidence")
            require(report["schedules_passed"] >= 10000 and len(profiles) >= 3, "cross-host schedule threshold not reached")
            report["cross_host_campaign_passed"] = True
        else:
            report["smoke_passed"] = True
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        for remote in remotes:
            remote.close()
        report["finished_utc"] = now()
        write_json(directory / "report.json", report)


class SyntheticControllerTests(unittest.TestCase):
    """No test here is evidence that a real cross-host workload ran."""
    def test_seeded_schedule_is_stable_and_directed(self):
        first = schedule(123, 4, "asymmetric")
        self.assertEqual(first, schedule(123, 4, "asymmetric"))
        self.assertNotEqual(first, schedule(124, 4, "asymmetric"))
        self.assertEqual(len(first["links"]), 6)
        for link in first["links"].values():
            self.assertEqual(set(link["actions"].values()), {"drop", "delay", "duplicate", "reorder"})
        self.assertNotEqual(first["links"]["1>2"]["base_delay_ms"], first["links"]["2>1"]["base_delay_ms"])

    def test_frame_crc_truncation_and_size_oracles(self):
        a, b = socket.socketpair()
        try:
            a.sendall(encode_frame({"hello": "fixture"}))
            self.assertEqual(read_frame(b)[1], {"hello": "fixture"})
            broken = bytearray(encode_frame({"x": 1}))
            broken[-1] ^= 1
            a.sendall(broken)
            with self.assertRaisesRegex(RuntimeError, "checksum"):
                read_frame(b)
            a.sendall(b"PBRPC001" + struct.pack("<II", MAX_FRAME + 1, 0))
            with self.assertRaisesRegex(RuntimeError, "length"):
                read_frame(b)
            a.sendall(b"PB")
            a.shutdown(socket.SHUT_WR)
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                read_frame(b)
        finally:
            a.close()
            b.close()

    def test_duplicate_machine_and_boot_oracle(self):
        inventory, hs = synthetic_enrollment()
        validate_handshakes(inventory, hs)
        hs[1]["boot_id_sha256"] = hs[0]["boot_id_sha256"]
        with self.assertRaisesRegex(RuntimeError, "boot"):
            validate_handshakes(inventory, hs)

    def test_container_and_artifact_pin_oracle(self):
        inventory, hs = synthetic_enrollment()
        hs[0]["container_marker"] = True
        with self.assertRaisesRegex(RuntimeError, "containers"):
            validate_handshakes(inventory, hs)
        hs[0]["container_marker"] = False
        hs[0]["binary_sha256"] = "b" * 64
        with self.assertRaisesRegex(RuntimeError, "pin mismatch"):
            validate_handshakes(inventory, hs)

    def test_shared_or_oversized_disk_refused(self):
        inventory, hs = synthetic_enrollment()
        hs[0]["storage"]["total_bytes"] = MAX_VOLUME + 1
        with self.assertRaisesRegex(RuntimeError, "bounded mount"):
            validate_handshakes(inventory, hs)
        hs[0]["storage"]["total_bytes"] = 128 * 1024 * 1024
        hs[0]["scratch"]["device_id"] = hs[0]["storage"]["device_id"]
        with self.assertRaisesRegex(RuntimeError, "must not contain"):
            validate_handshakes(inventory, hs)

    def test_export_rejects_unowned_evidence_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "unexpected evidence"):
                export_evidence(Path(temporary), 1, {"files": {"../../unowned": ""}})

    def test_real_proxy_delivery_loss_and_duplication_with_synthetic_peer(self):
        with SyntheticProxyFixture() as fixture:
            fixture.proxy.configure({"actions": {"1": "duplicate", "2": "drop"}})
            fixture.send(1)
            self.assertEqual(fixture.peer.received, [1, 1])
            with self.assertRaises((RuntimeError, OSError)):
                fixture.send(2)
            self.assertEqual(fixture.peer.received, [1, 1])
            self.assertEqual(fixture.proxy.counts["duplicate"], 1)
            self.assertEqual(fixture.proxy.counts["loss"], 1)

    def test_real_proxy_reordering_is_observed_not_assumed(self):
        with SyntheticProxyFixture() as fixture:
            fixture.proxy.configure({"actions": {"1": "reorder"}, "reorder_wait_ms": 1200})
            with ThreadPoolExecutor(max_workers=1) as pool:
                first = pool.submit(fixture.send, 1)
                wait_until(lambda: fixture.proxy.pending is not None, seconds=2, description="synthetic held frame")
                fixture.send(2)
                first.result(timeout=3)
            self.assertEqual(fixture.peer.received, [2, 1])
            self.assertEqual(fixture.proxy.counts["reordered"], 1)

    def test_real_proxy_delay_and_partial_install_with_synthetic_peer(self):
        with SyntheticProxyFixture() as fixture:
            fixture.proxy.configure({"actions": {"1": "delay"}, "delay_ms": 45})
            started = time.monotonic()
            fixture.send(1)
            self.assertGreaterEqual(time.monotonic() - started, 0.040)
            fixture.proxy.configure({}, interrupt_install=True)
            with self.assertRaises((RuntimeError, OSError)):
                fixture.send(2, "install")
            wait_until(lambda: fixture.peer.incomplete > 0, seconds=2, description="synthetic partial frame")
            self.assertEqual(fixture.peer.received, [1])
            self.assertEqual(fixture.proxy.counts["snapshot_transfer_disconnected"], 1)

    def test_legacy_or_client_packet_cannot_enter_peer_proxy(self):
        with SyntheticProxyFixture() as fixture:
            with socket.create_connection(address(fixture.listen), timeout=2) as stream:
                stream.sendall(encode_frame({"kind": "client", "command": {"op": "status"}}))
                with self.assertRaises((RuntimeError, OSError)):
                    read_frame(stream)
            self.assertFalse(fixture.peer.received)

    def test_converter_preserves_uncertainty_and_rejects_receipt_lies(self):
        calls = synthetic_wire_calls()
        calls[0]["reply"] = {"kind": "transport_uncertain", "message": "fixture timeout"}
        converted = checker_operations(calls)
        self.assertEqual(converted[0]["outcome"]["outcome"], "unknown")
        calls[0]["reply"] = {"kind": "error", "code": "capacity", "message": "never admitted"}
        self.assertEqual(checker_operations(calls)[0]["outcome"]["outcome"], "definitive_abort")
        calls = synthetic_wire_calls()
        calls[0]["reply"]["value"]["durable"] = False
        with self.assertRaisesRegex(RuntimeError, "contradict"):
            checker_operations(calls)
        calls = synthetic_wire_calls()
        calls[1]["command"]["query"]["predicate"] = "equals"
        with self.assertRaisesRegex(RuntimeError, "unsupported value filter"):
            checker_operations(calls)

    def test_absent_does_not_resolve_unknown_and_conflict_receipts_are_carried(self):
        for terminal in ["applied", "conflict"]:
            with self.subTest(terminal=terminal), tempfile.TemporaryDirectory(prefix="atlas-SYNTHETIC-resolution-") as temporary:
                scenario = Scenario({"partition": "ab" * 16}, [], schedule(1, 0, "lan"), Path(temporary), "SYNTHETIC")
                command = synthetic_wire_calls()[0]["command"]
                write = {"token": command["token"], "intent": command["intent"]}
                scenario.pending = [write]
                scenario.leader = lambda: 1
                observed = []
                replies = [{"kind": "ok", "value": {"status": "absent"}},
                           {"kind": "ok", "value": {"status": terminal, "durable": True, "position": "2", "term": "1"}}]
                def call(node, request):
                    observed.append(request)
                    return replies.pop(0)
                scenario.call = call
                scenario.reconcile()
                self.assertEqual([c["op"] for c in observed], ["outcome", "write"])
                self.assertEqual(observed[1], {"op": "write", **write})
                self.assertFalse(scenario.pending)
                self.assertEqual(scenario.receipts[write["token"]]["status"], terminal)
                self.assertEqual(bool(scenario.model), terminal == "applied")

    def test_unresolved_retries_fail_without_discarding_producer(self):
        with tempfile.TemporaryDirectory(prefix="atlas-SYNTHETIC-pending-") as temporary:
            scenario = Scenario({"partition": "ab" * 16}, [], schedule(1, 0, "lan"), Path(temporary), "SYNTHETIC")
            command = synthetic_wire_calls()[0]["command"]
            scenario.pending = [{"token": command["token"], "intent": command["intent"]}]
            scenario.leader = lambda: 1
            scenario.call = lambda node, request: {"kind": "transport_uncertain", "message": "fixture partition"}
            with self.assertRaisesRegex(RuntimeError, "lacks terminal"):
                scenario.reconcile()
            self.assertEqual(len(scenario.pending), 1)

    def test_data_release_requires_export_token_and_exact_owned_path(self):
        with tempfile.TemporaryDirectory(prefix="atlas-SYNTHETIC-release-") as temporary:
            root = Path(temporary)
            volume, evidence, unrelated = root / "volume", root / "evidence", root / "unrelated"
            volume.mkdir()
            evidence.mkdir()
            unrelated.mkdir()
            data = volume / "owned"
            data.mkdir()
            (data / "state").write_text("fixture")
            write_json(evidence / "ownership.json", {"uid": os.getuid(), "token": "fixture-token", "data": str(data)})
            agent = HostAgent.__new__(HostAgent)
            agent.enrollment = {"storage_mount": str(volume)}
            agent.completed = {"token": "fixture-token", "data": data, "root": evidence}
            with self.assertRaisesRegex(RuntimeError, "exported"):
                agent.release_data({"release_token": "wrong"})
            self.assertTrue((data / "state").is_file())
            released = agent.release_data({"release_token": "fixture-token"})
            self.assertTrue(released["owned_data_released"])
            self.assertFalse(data.exists())
            self.assertTrue(unrelated.is_dir())
            self.assertTrue((evidence / "ownership.json").is_file())

    def test_synthetic_conversion_runs_independent_checker_and_catches_wrong_value(self):
        require(CHECKER_EXECUTABLE is not None and CHECKER_EXECUTABLE.is_file(), "explicit public checker binary required")
        with tempfile.TemporaryDirectory(prefix="atlas-SYNTHETIC-checker-") as temporary:
            root = Path(temporary)
            good, bad = root / "good", root / "bad"
            good.mkdir()
            bad.mkdir()
            scenario = Scenario({"partition": "ab" * 16}, [], schedule(12, 0, "lan"), root, "SYNTHETIC_CODEC_FIXTURE")
            scenario.calls = synthetic_wire_calls()
            result = run_independent_checker(scenario, CHECKER_EXECUTABLE, good)
            self.assertEqual(result["operations_checked"], 2)
            scenario.calls[1]["reply"]["value"]["rows"][0]["value"] = "32"
            with self.assertRaisesRegex(RuntimeError, "did not establish"):
                run_independent_checker(scenario, CHECKER_EXECUTABLE, bad)
            # Negative controls for the public record+EOF protocol. These are
            # codec fixtures, not engine observations or checker executions.
            scenario.calls = synthetic_wire_calls()
            accepted = [strict_json(line) for line in (good / "checker-00.stdout.log").read_text().splitlines()]
            for ordinal, fault in enumerate(["missing_summary", "extra_output", "wrong_source", "wrong_seed", "wrong_count", "contradictory_summary"]):
                records = strict_json(json.dumps(accepted))
                if fault == "missing_summary":
                    records.pop()
                elif fault == "extra_output":
                    records.append(records[-1])
                elif fault == "wrong_source":
                    records[0]["checker_source_sha256"] = "0" * 64
                elif fault == "wrong_seed":
                    records[0]["seed"] += 1
                elif fault == "wrong_count":
                    records[1]["records"] += 1
                else:
                    records[1]["violations"] = 1
                output = "".join(json.dumps(record) + "\n" for record in records).encode()
                observed = subprocess.CompletedProcess([str(CHECKER_EXECUTABLE)], 0, stdout=output, stderr=b"")
                destination = root / f"SYNTHETIC-protocol-{ordinal}"
                destination.mkdir()
                with self.subTest(fault=fault), patch.object(subprocess, "run", return_value=observed), self.assertRaises(RuntimeError):
                    run_independent_checker(scenario, CHECKER_EXECUTABLE, destination)


def synthetic_wire_calls():
    return [{"node": 1, "invocation_ns": 1, "response_ns": 2,
             "command": {"op": "write", "token": "ab", "intent": {"reads": [{"key": "61", "value": None}], "mutations": [{"key": "61", "value": "31"}]}},
             "reply": {"kind": "ok", "value": {"position": "1", "term": "1", "status": "applied", "replayed": False, "durable": True, "wrote": True}}},
            {"node": 2, "invocation_ns": 3, "response_ns": 4,
             "command": {"op": "snapshot", "mode": "quorum", "minimum": None, "query": {"key_prefix": "", "predicate": "any", "value": ""}},
             "reply": {"kind": "ok", "value": {"position": "2", "term": "1", "mode": "quorum", "rows": [{"key": "61", "value": "31"}]}}}]


class SyntheticPeer:
    """Loopback codec fixture, deliberately not a database or host deployment."""
    def __init__(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.listener.settimeout(0.1)
        self.endpoint = f"127.0.0.1:{self.listener.getsockname()[1]}"
        self.stop, self.received, self.incomplete = threading.Event(), [], 0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop.is_set():
            try:
                stream, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with stream:
                stream.settimeout(2)
                try:
                    _, packet = read_frame(stream)
                    self.received.append(packet["message"]["body"]["fixture_id"])
                    stream.sendall(encode_frame({"kind": "ok", "value": {"accepted": True}}))
                except (OSError, RuntimeError):
                    self.incomplete += 1

    def close(self):
        self.stop.set()
        self.listener.close()
        self.thread.join(timeout=3)
        require(not self.thread.is_alive(), "synthetic peer did not stop")


class SyntheticProxyFixture:
    def __enter__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="atlas-SYNTHETIC-controller-")
        self.peer = SyntheticPeer()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.listen = f"127.0.0.1:{probe.getsockname()[1]}"
        self.proxy = PeerProxy(1, 2, self.listen, self.peer.endpoint,
                               Journal(Path(self.temporary.name) / "SYNTHETIC-proxy.jsonl"))
        return self

    def send(self, fixture_id, kind="append"):
        packet = {"kind": "atlas_peer", "protocol": 2,
                  "message": {"from": 1, "to": 2, "body": {"kind": kind, "fixture_id": fixture_id}}}
        with socket.create_connection(address(self.listen), timeout=2) as stream:
            stream.settimeout(3)
            stream.sendall(encode_frame(packet))
            return read_frame(stream)[1]

    def __exit__(self, *_):
        self.proxy.close()
        self.peer.close()
        self.temporary.cleanup()


def synthetic_enrollment():
    inventory = {"source_sha": "a" * 40, "agent_sha256": "a" * 64,
                 "binary_sha256": "a" * 64,
                 "hosts": [{"name": f"SYNTHETIC-{i}", "machine_id_sha256": str(i) * 64,
                            "node": i, "peer_ip": f"192.0.2.{i}", "node_port": 29001,
                            "proxy_ports": {str(n): 29010 + n for n in range(1, 4) if n != i}}
                           for i in range(1, 4)]}
    values = [{"agent_protocol": 1, "agent_sha256": "a" * 64,
               "binary_sha256": "a" * 64, "source_sha": "a" * 40,
               "machine_id_sha256": str(i) * 64, "boot_id_sha256": str(i + 3) * 64,
               "node": i, "allowed_peers": {str(n): f"192.0.2.{n}:29001" for n in range(1, 4)},
               "proxy_ports": {str(n): 29010 + n for n in range(1, 4) if n != i},
               "virtualization": "kvm", "container_marker": False,
               "independence_attestation": {"kind": "isolated_vm", "storage": True, "network": True,
                                            "clocks": True, "evidence": "SYNTHETIC UNIT FIXTURE; NEVER A RESULT"},
               "dedicated_volume": True, "storage": {"mountpoint": "/synthetic", "path": "/synthetic",
                                                       "total_bytes": 128 * 1024 * 1024, "device_id": 1, "filesystem": "ext4"},
               "scratch": {"device_id": 2}} for i in range(1, 4)]
    return inventory, values


def main():
    global CHECKER_EXECUTABLE
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    agent = sub.add_parser("agent", help="persistent SSH stdio agent; use only with administrator enrollment")
    agent.add_argument("--enrollment", type=Path, required=True)
    for name in ["inspect", "run"]:
        command = sub.add_parser(name)
        command.add_argument("--inventory", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        if name == "run":
            command.add_argument("--seed", type=int, default=20261025)
            command.add_argument("--schedules", type=int, default=3)
            command.add_argument("--profiles", nargs="+", choices=sorted(PROFILES), default=list(PROFILES))
            command.add_argument("--replay-schedule", type=Path)
            command.add_argument("--qualify", action="store_true",
                                 help="require full measured cross-host campaign; never verifies engine source or full release")
            command.add_argument("--checker-binary", dest="checker", type=Path, required=True,
                                 help="explicit public atlas-history-checker executable; no engine checkout is used")
    plan = sub.add_parser("plan", help="generate UNEXECUTED schedules; this is never evidence")
    plan.add_argument("--seed", type=int, default=20261025)
    plan.add_argument("--schedules", type=int, default=3)
    plan.add_argument("--output", type=Path, required=True)
    unit = sub.add_parser("self-test", help="synthetic controller unit tests; not cluster qualification")
    unit.add_argument("--checker-binary", type=Path, required=True,
                      help="explicit built public atlas-history-checker; missing path fails, never skips")
    args = parser.parse_args()
    if args.command == "agent":
        agent_main(args)
    elif args.command == "self-test":
        CHECKER_EXECUTABLE = args.checker_binary.resolve(strict=True)
        print("Synthetic controller tests only; actual cross-host schedules executed: 0", flush=True)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SyntheticControllerTests)
        require(unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful(), "synthetic controller tests failed")
    elif args.command == "plan":
        require(0 < args.schedules <= 100000 and 0 <= args.seed < 2**64, "bounded positive schedule count and u64 seed required")
        require(not args.output.exists(), "refuse overwriting schedule plan")
        write_json(args.output, {"schema": 1, "classification": "unexecuted_schedule_plan", "qualifying_results": False,
                                "schedules": [schedule(args.seed, i, list(PROFILES)[i % 3]) for i in range(args.schedules)]})
    else:
        if args.command == "run":
            require(0 < args.schedules <= 100000 and 0 <= args.seed < 2**64, "bounded positive schedule count and u64 seed required")
            require(not (args.qualify and args.replay_schedule), "a single replay cannot qualify the 10,000-schedule campaign")
        campaign(args)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"Atlas cross-host runner failed: {error}", file=sys.stderr)
        sys.exit(1)
