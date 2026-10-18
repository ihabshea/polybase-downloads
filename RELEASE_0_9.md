# Polybase 0.9.0 — Project Janus

Read the database at one exact retained commit position. Historical point reads,
byte-key ranges, typed JSON predicates and whole-word search observe complete
atomic transactions and keep deterministic byte-key ordering.

## Historical execution and explain

The read-only `as_of` APIs distinguish an empty answer from future, malformed or
expired positions. Historical pages keep their original query and position;
checkpoint and compaction preserve the documented retention boundary. A bounded,
disposable version cache accelerates warm reads without adding historical work
to the writer's publication path. Cold reconstruction can inspect the entire
retained baseline and WAL.

Additive diagnostics expose the captured position, chosen route, estimates,
actual reconstruction and query work, measured phase timings and fallback
reasons. Estimates are not measured durations. Existing result types and wire
fields remain compatible; WAL, checkpoint and cursor formats are unchanged.

Read [the complete Janus contract](JANUS_0_9.md) or use the
[interactive guide](https://base.polymathlabs.xyz/janus-0-9.html). Its commit
explorer is an illustrative fixture, separate from the measurements.

## Recorded measurements and limits

The native Linux qualification matrix covers 36 historical cases over 1K, 10K
and 100K records, including ordered parity against the reference and forced Scan.
All warm historical targets pass under the recorded conditions. Seven of twelve
current-head cases miss the 10% p50/p95 regression goal. Cold reconstruction
reaches about 1.996 seconds; cumulative process peak RSS reaches 200,524 KiB.

These measurements were recorded on the shared Linux host with Rust 1.99.1.
They do not predict another machine's performance. The first invalidated run is
preserved separately and excluded from qualification. Download
[all raw samples and provenance](benchmarks/0.9.0/results.json), including every
counterexample, source and executable fingerprints, limits and machine details.

## Qualification and compatibility

Local formatting, warnings-as-errors workspace Clippy and all 227 workspace tests
pass. Rust 1.89 compatibility also passes. The recorded deterministic qualification
covers 1,600 operations, 836 historical checks, eleven expired cursors and 37 real
process-crash scenarios. These are software recovery checks and do not establish
hardware power-loss guarantees.

[Platform qualification](qualification/0.9.0/README.md) records the exact published
archives, extracted-runtime acceptance, malformed-archive rejection, runnable
documentation, staging protection and bidirectional 0.8.2/0.9 upgrade checks.
The Mac package is built and tested natively on Apple Silicon macOS 15.1. The
published Linux package is built and tested in an x86-64 Ubuntu 22.04/glibc 2.35
container under Docker emulation on Apple Silicon. Earlier native Linux candidate
qualification is separate evidence; its archive hash differs.

Distribution builds pin Rust 1.99.0 and clean private source
`4dccc0ff6593f044c6fb9237ca7c7bd891b4ec45`. Hosted GitHub CI never started because
of an account billing/spending restriction. Local qualification is not a hosted
CI pass. The public website separately passes 196 responsive checks, 80
accessibility scans and seven behavior checks.

Published SDKs remain at 0.8.3 for existing operations. SDK 0.9.0 historical
helpers remain a separately qualified, unpublished candidate; use the documented
HTTP routes for those operations. Website installation commands retain the
published SDK versions.

Apple Silicon Mac requires macOS 15+; executables are ad-hoc signed and not
notarized. Linux requires x86-64 and glibc 2.35+ (Ubuntu 22.04+). Each archive
contains five executables. This is a bounded local evaluation under the included
terms, with private engine source and separately MIT-licensed clients. Hosted
SaaS is coming soon.
