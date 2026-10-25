#!/usr/bin/env python3
"""MIT QA codec-only fixtures; no engine or cross-host workload executes."""
import json
import socket
import struct
import threading
import unittest
from unittest.mock import patch
import zlib

from cluster_driver import MAX_FRAME, RpcError, rpc, rpc_reply


class RpcCodecTests(unittest.TestCase):
    def exchange(self, response, command=None, raw_frame=None):
        reader, writer = socket.socketpair()
        request = {}
        fixture_errors = []

        def fixture():
            with writer:
                def exact(size):
                    data = bytearray()
                    while len(data) < size:
                        block = writer.recv(size - len(data))
                        if not block:
                            raise RuntimeError("fixture request truncated")
                        data.extend(block)
                    return data
                header = exact(16)
                size, crc = struct.unpack("<II", header[8:])
                body = exact(size)
                self.assertEqual(zlib.crc32(body), crc)
                request.update(json.loads(body))
                payload = json.dumps(response).encode()
                frame = b"PBRPC001" + struct.pack("<II", len(payload), zlib.crc32(payload)) + payload
                writer.sendall(frame if raw_frame is None else raw_frame)

        def checked_fixture():
            try:
                fixture()
            except BaseException as error:
                fixture_errors.append(repr(error))

        thread = threading.Thread(target=checked_fixture, daemon=True)
        thread.start()
        try:
            with patch("cluster_driver.socket.create_connection", return_value=reader):
                value = (command or rpc_reply)("127.0.0.1:29001", {"op": "status"})
            self.assertEqual(request, {"kind": "client", "command": {"op": "status"}})
            return value
        finally:
            reader.close()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
            self.assertFalse(fixture_errors, fixture_errors)

    def test_success_exact_framing_and_value_helper(self):
        reply = {"kind": "ok", "value": {"node": "1", "role": "follower"}}
        self.assertEqual(self.exchange(reply), reply)
        self.assertEqual(self.exchange(reply, command=rpc), reply["value"])

    def test_structured_errors_preserve_unknown_and_leader_hint(self):
        reply = {"kind": "error", "code": "uncertain", "message": "outcome unknown", "leader": 2}
        self.assertEqual(self.exchange(reply), reply)
        with self.assertRaises(RpcError) as raised:
            self.exchange(reply, command=rpc)
        self.assertEqual(raised.exception.reply, reply)
        self.assertEqual(raised.exception.code, "uncertain")
        self.assertEqual(raised.exception.leader, 2)

    def test_crc_size_truncation_and_duplicate_fields_rejected(self):
        frames = [
            b"PBRPC001" + struct.pack("<II", 2, 0) + b"{}",
            b"PBRPC001" + struct.pack("<II", MAX_FRAME + 1, 0),
            b"PB",
        ]
        duplicate = b'{"kind":"ok","kind":"error","value":{}}'
        frames.append(b"PBRPC001" + struct.pack("<II", len(duplicate), zlib.crc32(duplicate)) + duplicate)
        for frame in frames:
            with self.subTest(frame=frame[:16]), self.assertRaises(RuntimeError):
                self.exchange({}, raw_frame=frame)

    def test_no_default_endpoint_or_unbounded_timeout(self):
        for timeout in [0, -1, 31]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                rpc_reply("127.0.0.1:29001", {"op": "status"}, timeout=timeout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
