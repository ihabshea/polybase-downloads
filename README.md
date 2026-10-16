# Polybase downloads

Official free evaluation downloads for Polybase, an independent database research project. The database source stays private. A hosted Polybase SaaS is coming soon.

Get the preview and documentation at **https://base.polymathlabs.xyz/download.html**.

The 0.8.0-preview.1 release provides Apple Silicon macOS 15+ and x86-64 Linux with glibc 2.35+ (Ubuntu 22.04+). Each archive contains four executables, installation and operational guides, evaluation terms, dependency notices, a build manifest and file hashes. Rust, Node and a cloud account are not required. Python 3.10+ is needed only for the optional three-node launcher.

Mac executables are ad-hoc signed and not notarized. Linux executables are unsigned. Use disposable data for this experimental preview. The [evaluation license](LICENSE) permits personal or internal evaluation, experimentation and development; production use and commercial redistribution are outside those terms.

Use any collection names: tasks, notes, projects, readings or your own records. Collections are key prefixes such as `tasks/1` and `notes/1`; values can be JSON, text or binary bytes. No collection registration or predefined business fields are required. The [collection guide](https://base.polymathlabs.xyz/docs.html#collections) explains queries and atomic writes across collections.

[Installation](INSTALLATION.md) · [Three-node lab](REPLICATION.md) · [Release notes](https://base.polymathlabs.xyz/release-notes.html)

This repository contains distribution documentation and versioned executable assets. It contains no database source, database directories or user data.

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
