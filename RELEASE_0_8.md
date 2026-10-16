# 0.8.0-preview.1 — query planning and qualification

Fresh current-head JSON pages now choose Scan or IndexLookup. Eligible scalar
`eq` predicates, including necessary equalities under nested `all`, can use a
declared covering index. Every candidate is checked against canonical values
with the entire residual predicate. Typed 1 and 1.0 remain equal; missing and
null stay distinct. Metadata, posting lists and values share one captured head
under the history gate. Historical continuations and live deltas/resume retain
the verified 0.7 paths. Index memory is derived and rebuilt from canonical state.

## Supported scope

One declared equality index is selected by actual posting cardinality, with a
deterministic name tie-break. No OR union, index intersection, range/compound
lookup, join, background build, cost estimate or optimal-plan claim is made.
Missing, invalid, out-of-range or unusable indexes fall back to bounded ordered
scans. Page rows/bytes, predicate limits and the shared index budget apply on
both paths. Candidate lists are borrowed, not expanded into unbounded arrays.
Explain reports actual candidates, execution rows, metadata/build rows and time.
Ordinary execution and EXPLAIN share one implementation; forced scan is available.

## Actual qualification

Measured implementation source SHA: `b7e15af1916b5444cba59b6deff5d8e6a7a5a834`.
Source tree SHA-256: `7a1d6d539894141bf3bb45e329e1d3122f818dc23714ba8d448fa8dfce23b116`.
Executable SHA-256: `51fe53cdb713d8693b8e0468d868a8a7533955ee136ce97d46ed56f0ece606e2`.
The source was clean at measurement. Exact UTC timestamps and all raw samples
are in [the raw results](benchmarks/0.8.0-preview.1/results.json). These are measured results, not target workload sizes.

| Records | Selectivity | Lookup median / p95 (ms) | Scan median / p95 (ms) | Canonical rows: lookup / scan |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 1% | 0.009 / 0.034 | 0.373 / 0.426 | 10 / 1,000 |
| 1,000 | 10% | 0.047 / 0.061 | 0.381 / 0.417 | 100 / 1,000 |
| 1,000 | 90% | 0.378 / 0.428 | 0.406 / 0.482 | 900 / 1,000 |
| 10,000 | 1% | 0.066 / 0.083 | 3.802 / 4.222 | 100 / 10,000 |
| 10,000 | 10% | 0.586 / 0.686 | 3.850 / 4.240 | 1,000 / 10,000 |
| 10,000 | 90% | 4.650 / 5.019 | 4.212 / 5.285 | 9,000 / 10,000 |
| 100,000 | 1% | 0.919 / 1.087 | 40.585 / 43.906 | 1,000 / 100,000 |
| 100,000 | 10% | 7.571 / 8.823 | 40.538 / 42.674 | 10,000 / 100,000 |
| 100,000 | 90% | 59.972 / 61.601 | 46.965 / 53.289 | 90,000 / 100,000 |

| Records | Cold build (ms) | Build rows | Process peak RSS (KiB) |
| ---: | ---: | ---: | ---: |
| 1,000 | 6.369 | 1,003 | 5,104 |
| 10,000 | 67.835 | 10,003 | 31,220 |
| 100,000 | 787.794 | 100,003 | 289,352 |

Latencies measure native engine calls, excluding HTTP encoding/network time.

All nine cases returned identical complete ordered results on both paths for
all 21 samples, after three warmups. Order alternated between paths. Lookup
significantly reduced work at 1% and 10%; at 90% it can be slower than scanning.
The planner has no cost model and does not claim the best latency for every
selectivity. Cold builds are timed separately and can dominate the first query.

Host: `Linux-6.18.44-x86_64-with-glibc2.41`, `rustc 1.99.1 (58cf8f9c3 2026-10-13)`, 5 available CPUs,
35743784960 reported RAM bytes, release profile, warm shared-host filesystem.
The complete-result qualification explicitly used 256 MiB logical index budget,
100,000 returned rows and 64 MiB result-byte cap. Defaults remain unchanged.
VmHWM is cumulative process peak RSS including seeding/recovery, index and query
results, not per-query allocation. Allocation counts are unavailable, not estimated.
No cold-cache, hardware power-loss, production throughput or RSS-bound claim is made.

## Correctness evidence

Local required checks passed: formatting, all-target/all-feature Clippy, 180
all-feature workspace tests and 150 default engine tests. New tests cover exact
numeric equivalence, missing/null, conjunction residuals, index deletion, cold and
warm budget failure, arbitrary ranges, byte/row limits, zero duplicates, generated
differential cases, reopen/checkpoint/compaction, live resume and controlled
multi-key publication races. An injected failure after durable sync fences the
instance; reopening rebuilds correct postings. Rust and TypeScript HTTP clients,
console handlers and shared explain/ordinary execution are tested directly.

## Reproduction and release status

For source maintainers:

```sh
python3 scripts/run-planning-bench.py target/new-planning-evidence --sizes 1000 10000 100000 --samples 21
```

Use an empty output directory. Before/after source digests must agree. Package
qualification and downloadable assets are recorded separately below; the measured
benchmark host above differs from the local release build environments. Existing
0.7 assets remain unchanged. Hosted SaaS remains forthcoming.

## Evaluation package publication

Clean package source: `97765a338bd3db31d90859710e1daa17d4bb9f83`.
The website refresh and merge do not change any binary or bundled-guide input.

| Target | SHA-256 |
| --- | --- |
| Apple Silicon macOS 15+ | `67bd60c43f06e790e55d50615a9c5cd09fba7449b6fd3f980fee9f46c5a6ee4f` |
| x86-64 Linux, glibc 2.35+ | `f8c3f5a8ed3eef97782ac1dc232c7f64cc40edb4acdefaa9cfac7297ee0c7fa5` |

Both extracted packages pass 18 runtime checks, including the new planner,
forced-scan parity, dropped-index fallback, restart, strict corruption handling
and failover receipt preservation. Archive mutation rejection, staging protection
and all five runnable documentation cases pass on both targets. Mac binaries
are ad-hoc signed, not notarized. Linux qualification uses Ubuntu 22.04 under
Docker x86-64 emulation on an Apple Silicon Mac. The staging check uses a
600-second build timeout in that environment; its boundary assertions are unchanged.
Hosted CI did not execute runner steps; these are local results.

[Download the evaluation](https://base.polymathlabs.xyz/download.html).
Checksums compare integrity and are not publisher signatures. Source remains
private; hosted SaaS is coming soon.
