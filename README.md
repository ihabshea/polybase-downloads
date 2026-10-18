# Polybase downloads

Official free evaluation downloads for Polybase, an independent database research project. The database source stays private. A hosted Polybase SaaS is coming soon.

Get the preview and documentation at **https://base.polymathlabs.xyz/download.html**.

The 0.8.2 release provides Apple Silicon macOS 15+ and x86-64 Linux with glibc 2.35+ (Ubuntu 22.04+). Each archive contains four executables, installation and operational guides, evaluation terms, dependency notices, a build manifest and file hashes. Rust, Node and a cloud account are not required. Python 3.10+ is needed only for the optional three-node launcher.

Mac executables are ad-hoc signed and not notarized. Linux executables are unsigned. Use disposable data for this experimental preview. The [evaluation license](LICENSE) permits personal or internal evaluation, experimentation and development; production use and commercial redistribution are outside those terms.

Use any collection names: tasks, notes, projects, readings or your own records. Collections are key prefixes such as `tasks/1` and `notes/1`; values can be JSON, text or binary bytes. No collection registration or predefined business fields are required. The [collection guide](https://base.polymathlabs.xyz/docs.html#collections) explains queries and atomic writes across collections.

[Installation](INSTALLATION.md) · [Three-node lab](REPLICATION.md) · [Release notes](https://base.polymathlabs.xyz/release-notes.html)

This repository contains distribution documentation, versioned executable assets
and the standalone [MIT client SDK source](clients/README.md). It contains no
database engine/server source, database directories or user data.

## Client SDKs

Install `@polymathbase/polybase-client@0.8.3` from npm or
`polybase-client@0.8.3` from crates.io. See the
[client installation and source guide](clients/README.md). These client SDKs have
their own MIT licenses; the binary evaluation terms remain unchanged.

## Project Janus — 0.9 candidate

Janus adds read-only point, range, typed JSON and whole-word queries at an exact
retained commit position, with measured explain diagnostics and deterministic
reference-model/crash verification. Read the [candidate release notes](RELEASE_0_9.md),
[historical query contract](JANUS_0_9.md), [measured benchmark evidence](benchmarks/0.9.0/README.md)
and [seeded/crash verification](qualification/0.9.0/verification/README.md).

All 36 historical benchmark cases passed correctness and the warm historical
targets. Seven of 12 current-head cases missed the 10% performance goal; every
miss and raw sample is retained. The 0.9 downloadable release and website remain
gated on matching native packages and publication. The published database is
still 0.8.2 and the published SDKs are still 0.8.3; candidate SDK sources here are
0.9.0.

## 0.7.0-preview.1

The 0.7.0-preview.1 prerelease is available in the versioned releases.

## 0.8.0-preview.1

Read [release notes and measured qualification](RELEASE_0_8.md),
[the planner contract](PREVIEW_0_8.md) and
[raw three-size/selectivity results](benchmarks/0.8.0-preview.1/results.json).
Matching clean-source Mac and Linux evaluation archives are distributed through
[the versioned release](https://github.com/ihabshea/polybase-downloads/releases/tag/v0.8.0-preview.1).
Both pass 18 extracted-runtime checks, archive rejection, staging protection and
runnable documentation examples. The Linux build and runtime qualification use
an x86-64 Ubuntu 22.04 container under Docker emulation on Apple Silicon.

## 0.8.2 — the complete 0.8 release

The [combined release notes](RELEASE_0_8_2.md) introduce the original 0.8 query
planner together with 0.8.2 adaptive execution: selectivity-aware costs, bounded
AND/OR plans, one snapshot-safe restart and additive diagnostics.
Read [the adaptive execution contract](PREVIEW_0_8_2.md),
[raw 60-case measurements](benchmarks/0.8.2/results.json) and
[platform qualification and upgrade evidence](qualification/0.8.2/README.md).
Matching clean-source Mac and Linux packages, checksums and runtime receipts are
in [the versioned release](https://github.com/ihabshea/polybase-downloads/releases/tag/v0.8.2).
The earlier 0.8 preview remains available in release history.
