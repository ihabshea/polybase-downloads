#!/usr/bin/env python3
"""Mutate a real candidate archive to verify rejection at the distribution boundary."""
import hashlib
import gzip
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile

spec = importlib.util.spec_from_file_location("verifier", Path(__file__).with_name("verify-release.py"))
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
source = Path(sys.argv[1])
verifier.verify(source, allow_dirty=True)
with tarfile.open(source) as tar:
    original = [(member, tar.extractfile(member).read()) for member in tar.getmembers()]

cases = ["private source file", "path traversal", "symlink", "duplicate path", "binary byte damage"]
for case in cases:
    with tempfile.TemporaryDirectory(prefix="polybase-package-rejection-") as temporary:
        archive = Path(temporary) / source.name
        with archive.open("wb") as raw, gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as zipped, tarfile.open(fileobj=zipped, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            for index, (member, data) in enumerate(original):
                if case == "binary byte damage" and member.name.endswith("/bin/polybase"):
                    data = data[:-1] + bytes([data[-1] ^ 1])
                if case == "path traversal" and index == 0:
                    member = tarfile.TarInfo("../../escaped-source")
                    member.size, member.mode = len(data), 0o644
                if case == "symlink" and index == 0:
                    member = tarfile.TarInfo(member.name)
                    member.type, member.linkname = tarfile.SYMTYPE, "/etc/passwd"
                    member.size = 0
                    data = b""
                tar.addfile(member, io.BytesIO(data))
            if case in ("private source file", "duplicate path"):
                member = tarfile.TarInfo(original[0][0].name if case == "duplicate path"
                                         else original[0][0].name.split("/")[0] + "/crates/engine/src/lib.rs")
                member.size = 6
                tar.addfile(member, io.BytesIO(b"source"))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(archive.suffix + ".sha256").write_text(f"{digest}  {archive.name}\n")
        try:
            verifier.verify(archive, allow_dirty=True)
        except (ValueError, KeyError) as error:
            print(f"PASS rejected {case}: {error}")
        else:
            raise AssertionError(f"accepted {case}")
print("PASS legitimate candidate and five altered archives")

for case in ["extra gzip member", "hidden tar trailer", "PAX extension before allocation", "member padding", "optional gzip metadata"]:
    with tempfile.TemporaryDirectory(prefix="polybase-container-rejection-") as temporary:
        archive = Path(temporary) / source.name
        if case == "extra gzip member":
            archive.write_bytes(source.read_bytes() + gzip.compress(b"synthetic hidden payload"))
        elif case == "hidden tar trailer":
            archive.write_bytes(gzip.compress(gzip.decompress(source.read_bytes()) + b"synthetic hidden payload"))
        elif case == "PAX extension before allocation":
            header = tarfile.TarInfo("extended-metadata")
            header.type = tarfile.XHDTYPE
            header.size = 256 * 1024 * 1024
            archive.write_bytes(gzip.compress(header.tobuf(format=tarfile.USTAR_FORMAT) + bytes(tarfile.RECORDSIZE - tarfile.BLOCKSIZE)))
        elif case == "member padding":
            inflated = bytearray(gzip.decompress(source.read_bytes()))
            with tarfile.open(fileobj=io.BytesIO(inflated), mode="r:") as tar:
                member = next(item for item in tar.getmembers() if item.name.endswith("/GUARANTEES.md"))
            offset = member.offset_data + member.size
            assert member.size % tarfile.BLOCKSIZE < tarfile.BLOCKSIZE - 16
            inflated[offset:offset + 16] = b"unlisted padding"
            archive.write_bytes(gzip.compress(inflated))
        else:
            original_gzip = source.read_bytes()
            archive.write_bytes(original_gzip[:3] + b"\x10" + original_gzip[4:10] + b"unlisted comment\0" + original_gzip[10:])
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(archive.suffix + ".sha256").write_text(f"{digest}  {archive.name}\n")
        try:
            verifier.verify(archive, allow_dirty=True)
        except ValueError as error:
            print(f"PASS rejected {case}: {error}")
        else:
            raise AssertionError(f"accepted {case}")
