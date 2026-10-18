# Polybase 0.9.0 Linux candidate qualification

This is a qualified Linux candidate, not a downloadable full release. Native Mac qualification and final website deployment remain pending. The live database release remains 0.8.2 and registry SDKs remain 0.8.3.

- Clean package source: `4dccc0ff6593f044c6fb9237ca7c7bd891b4ec45`.
- Engine tree: `768dd1236194e4c6de833f09c1cdb86372fd24cc`, identical to the valid benchmark implementation at `6a123302edad0ed49cac541615b9719bb007d188`.
- Archive: `polybase-0.9.0-x86_64-unknown-linux-gnu.tar.gz`, 3,408,862 bytes.
- Archive SHA-256: `81b2fefea6e36dfcb726edbad5e4e502018fbd5a67611a23c0bac06f8e0ce83c`.
- Build: pinned Rust 1.99.0, default features, native x86-64. All five executables are included. No fault-injection feature is enabled.

## Observed acceptance

Native Linux/glibc 2.41 and native x86-64 Ubuntu 22.04/glibc 2.35 both pass 21 extracted-runtime checks, ten deliberately unsafe/altered archive cases, five runnable documentation cases and seven bidirectional upgrade checks. The staging checksum-symlink refusal also passes natively. All five ELF binaries require at most GLIBC 2.34 versioned symbols; actual execution on glibc 2.35 is recorded separately rather than inferred from symbol inspection.

The runtime receipts include read-only historical point/range/typed JSON/text, complete atomic snapshots, EXPLAIN, historical continuation across writes, explicit malformed/future/expired positions, checkpoint, compaction and reopen. The fifth private-pipe executable is exercised for identity, atomic batch, ordered scan and immediate close/reopen.

The old input is the genuine anonymously downloaded published 0.8.2 archive, source `2a8fd5c95ade14b05be9cfd66c419c0d68b6500f`, SHA-256 `dbec2441bde1cb880c931459ff8b23c14aa68accb5fcb154d587ede00a88eb10`. The archived verifier and independently recorded published hash are used before extraction. The fixture preserves old named retries after a discarded acknowledgment, old/new subscription and page cursors, revision CAS, exact event ordering, both directions of checkpoint/WAL reopening and explicit history expiry. A discarded acknowledgment in this fixture is separate from the 37 actual injected-process-crash cases in the seeded qualification.

The Ubuntu runtime uses the host Linux kernel without emulation and disables network egress for acceptance. Base image: `ubuntu:22.04@sha256:0a9887931b0e38af2e3487ed39e29436b0535c4f3f52e57745baaf79d1898956`; resolved qualification image ID: `sha256:bc046274091614dbaba895987fb38ac7c9d070397a63bad7df29ac735d2b3a36`. Actual glibc is 2.35. Exact installed packages and image identity are retained. Build-time system/proxy CA trust uses secret mounts and leaves TLS verification enabled; no credential or session CA is included in these artifacts.

## Evidence inventory

`acceptance.json`, `documentation-examples.json`, `upgrade-compatibility.json`, `glibc-symbols.json` and `staging-protection.json` record native checks. `ubuntu22/` contains the independent minimum-userspace receipts and raw stdout/stderr. `package-manifest.json` records the allowlisted package inventory, executable hashes, exact build command and toolchains. `host-environment.json`, `docker-image.json` and `docker-packages.txt` describe the qualification environment. `SHA256SUMS` covers every proof file.

The `tools/` directory contains only public archive/HTTP qualification scripts, examples and the versioned old verifier. It includes no engine/server Rust implementation, registry credentials or database data. The candidate archive is not included in this proof folder.

## Reproduce from the two archives

Use an x86-64 Linux host and provide the qualified 0.9 candidate locally. Preserve the archive checksum files beside both inputs. Obtain the published old archive and checksum from:

`https://github.com/ihabshea/polybase-downloads/releases/download/v0.8.2/polybase-0.8.2-x86_64-unknown-linux-gnu.tar.gz`

The matching checksum URL adds `.sha256`. The upgrade script independently pins the old archive hash above.

```sh
python3 tools/scripts/verify-release.py /absolute/path/to/polybase-0.9.0-x86_64-unknown-linux-gnu.tar.gz --expected-sha256 81b2fefea6e36dfcb726edbad5e4e502018fbd5a67611a23c0bac06f8e0ce83c --runtime --report replay-native.json
python3 tools/scripts/test-release-package.py /absolute/path/to/polybase-0.9.0-x86_64-unknown-linux-gnu.tar.gz
python3 tools/website/verify-examples.py /absolute/path/to/polybase-0.9.0-x86_64-unknown-linux-gnu.tar.gz --report replay-docs.json
python3 tools/glibc-symbols.py /absolute/path/to/polybase-0.9.0-x86_64-unknown-linux-gnu.tar.gz --verifier tools/scripts/verify-release.py --report replay-glibc.json
python3 tools/upgrade-check.py --old-package /absolute/path/to/polybase-0.8.2-x86_64-unknown-linux-gnu.tar.gz --new-package /absolute/path/to/polybase-0.9.0-x86_64-unknown-linux-gnu.tar.gz --old-verifier tools/verify-release-0.8.2.py --new-verifier tools/scripts/verify-release.py --report replay-upgrade.json
```

For isolated Ubuntu 22.04 acceptance, the following is the managed-cloud recipe. It preserves Docker registry/proxy configuration, redirects only writable Buildx metadata and supplies the existing system/proxy CA files as build secrets. On another environment supply its appropriate trusted CA files; keep HTTPS verification enabled. `readelf` is needed only for the separate host symbol inspection.

```sh
mkdir -p empty-context replay-ubuntu22
BUILDX_CONFIG="$PWD/.buildx" env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock build --secret id=system_ca,src=/etc/ssl/certs/ca-certificates.crt --secret id=proxy_ca,src="$CODEX_PROXY_CERT" --file Dockerfile --tag polybase-janus-runtime22:qualification empty-context
JANUS_NEW_ASSET_DIR=/absolute/directory/containing/new/archive
JANUS_OLD_ASSET_DIR=/absolute/directory/containing/old/archive
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock run --rm --network=none --env NO_PROXY=127.0.0.1,localhost --mount "type=bind,src=$PWD/tools,dst=/qualification,readonly" --mount "type=bind,src=$JANUS_NEW_ASSET_DIR,dst=/artifacts,readonly" --mount "type=bind,src=$JANUS_OLD_ASSET_DIR,dst=/old,readonly" --mount "type=bind,src=$PWD/replay-ubuntu22,dst=/receipts" polybase-janus-runtime22:qualification python3 /qualification/run-container-checks.py --new-package /artifacts/polybase-0.9.0-x86_64-unknown-linux-gnu.tar.gz --old-package /old/polybase-0.8.2-x86_64-unknown-linux-gnu.tar.gz --report-dir /receipts
```

The qualification commands explicitly cleared inherited Docker endpoint/context/TLS selectors before selecting the managed local socket, while preserving `DOCKER_CONFIG` and registry credentials. Reproduce that selection if your environment sets those selectors. Package and runtime assertions are unchanged. Docker apt package mirrors can later advance; compare the recorded package inventory and image identity when interpreting a replay.

These are process/recovery and local filesystem tests, not a proof of sudden power-loss behavior or production fitness. Hosted GitHub CI previously failed before runner steps because of account billing/spending limits, and no hosted pass is claimed. This environment has no native Mac runner, registry publication credentials or Sites deployment capability. Linux qualification does not satisfy those remaining publication gates.
