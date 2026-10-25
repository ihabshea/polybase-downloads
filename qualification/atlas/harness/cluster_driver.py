#!/usr/bin/env python3
"""MIT QA RPC client for operator-provided Polybase nodes, not a server.

Only sends an explicitly supplied framed client command. No engine, database
fixture, process launcher, credentials, or default endpoint is included.
"""
import argparse
import ipaddress
import json
import socket
import struct
import time
import zlib

MAX_FRAME = 2 * 1024 * 1024


class RpcError(RuntimeError):
    def __init__(self, reply):
        self.reply = reply
        self.code = reply["code"]
        self.leader = reply.get("leader")
        super().__init__(f"{self.code}: {reply['message']}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError(f"duplicate RPC JSON field: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise RuntimeError(f"nonfinite RPC JSON value: {value}")


def exact(stream, size, deadline):
    result = bytearray()
    while len(result) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("RPC read deadline")
        stream.settimeout(remaining)
        block = stream.recv(size - len(result))
        if not block:
            raise RuntimeError("incomplete RPC frame")
        result.extend(block)
    return bytes(result)


def rpc_reply(endpoint, command, timeout=5):
    """Return the exact structured `ok` or `error` reply; never infer an abort."""
    if not isinstance(command, dict) or not 0 < timeout <= 30:
        raise ValueError("explicit object command and timeout in (0,30] required")
    host, port = endpoint.rsplit(":", 1)
    ipaddress.IPv4Address(host)
    if not 1 <= int(port) <= 65535:
        raise ValueError("invalid TCP port")
    payload = json.dumps({"kind": "client", "command": command}, separators=(",", ":"),
                         allow_nan=False).encode()
    if not 0 < len(payload) <= MAX_FRAME:
        raise ValueError("RPC payload outside bounded frame")
    deadline = time.monotonic() + timeout
    with socket.create_connection((host, int(port)), timeout=timeout) as stream:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("RPC connection deadline")
        stream.settimeout(remaining)
        stream.sendall(b"PBRPC001" + struct.pack("<II", len(payload), zlib.crc32(payload)) + payload)
        header = exact(stream, 16, deadline)
        if header[:8] != b"PBRPC001":
            raise RuntimeError("unsupported RPC frame")
        size, crc = struct.unpack("<II", header[8:])
        if not 0 < size <= MAX_FRAME:
            raise RuntimeError("RPC reply outside bounded frame")
        body = exact(stream, size, deadline)
        if zlib.crc32(body) != crc:
            raise RuntimeError("RPC reply checksum mismatch")
    reply = json.loads(body, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(reply, dict) or reply.get("kind") not in {"ok", "error"}:
        raise RuntimeError("unsupported RPC reply kind")
    if reply["kind"] == "ok" and "value" not in reply:
        raise RuntimeError("RPC success has no value")
    if reply["kind"] == "error" and not all(isinstance(reply.get(k), str) for k in ["code", "message"]):
        raise RuntimeError("malformed structured RPC error")
    return reply


def rpc(endpoint, command, timeout=5):
    """Compatibility helper: return successful value or raise structured RpcError.

    A transport exception or uncertain write reply is not a definite abort.
    Preserve the same token/intent for a later named outcome lookup or retry.
    """
    reply = rpc_reply(endpoint, command, timeout)
    if reply["kind"] == "error":
        raise RpcError(reply)
    return reply["value"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", required=True)
    parser.add_argument("--command", required=True, help="explicit client command as JSON")
    args = parser.parse_args()
    command = json.loads(args.command, object_pairs_hook=unique_object, parse_constant=reject_constant)
    print(json.dumps(rpc_reply(args.address, command), indent=2))
