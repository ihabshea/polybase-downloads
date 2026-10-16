# Polybase 0.8.2 — Adaptive Query Execution candidate

Current-head JSON queries compare dimensionless Scan and indexed costs using disposable captured-head statistics. Eligible plans include a single equality lookup, an ordered two-index AND intersection and a covered, deduplicated OR union. Every candidate evaluates the complete predicate against canonical data. An inaccurate estimate may cause one bounded Scan restart while the original history gate stays held.

Existing Rust result structs, enum variants and method signatures remain unchanged. New diagnostic APIs and additive HTTP EXPLAIN fields expose alternatives, estimates, actual work, statistics epochs, replan reasons and measured phase timings. Optional process-local calibration is disabled after reopen. WAL, durable index definitions, historical cursors and subscription semantics retain their prior formats and paths.

[Execution contract and limitations](PREVIEW_0_8_2.md) · [Full benchmark evidence](benchmarks/0.8.2/README.md) · [Raw samples](benchmarks/0.8.2/results.json)

## Measured performance

All 60 cases passed complete ordered forced-Scan parity, with zero duplicates, across five cold and 21 warm samples per path. Sizes: 1,000, 10,000 and 100,000; exact result selectivities: 0.1%, 1%, 10%, 50% and 90%; families: equality, correlated AND, independent AND and independent OR. Cold means disposable cache rebuild after reopen, with reopen excluded and OS caches uncontrolled.

| 100K equality selectivity | Auto p50 / p95 (ms) | Scan p50 / p95 (ms) | Initial strategy | Scan / Auto p50 |
| ---: | ---: | ---: | --- | ---: |
| 0.1% | 0.220 / 0.326 | 52.529 / 55.528 | index_lookup | 239.20× |
| 1% | 1.156 / 1.973 | 53.402 / 59.562 | index_lookup | 46.21× |
| 10% | 10.007 / 12.357 | 48.224 / 50.519 | index_lookup | 4.82× |
| 50% | 55.087 / 71.323 | 53.789 / 58.874 | scan | 0.98× |
| 90% | 55.402 / 59.549 | 55.606 / 64.826 | scan | 1.00× |

The 1% equality workload measured 46.21× warm speedup against Scan, exceeding the 35.36× goal (80% of the historical 44.2×). The 90% equality workload initially selected Scan. Absolute times and raw samples remain available; shared-host runs are not production capacity claims.

## Measured counterexamples

At 100K, correlated 50% AND chose an intersection and restarted: Auto median 71.726 ms versus 45.458 ms Scan, or 1.578× slower. The attempt examined 36,459 canonical candidates and consumed 72,918 posting keys before a complete 100,000-row Scan. Results remained identical. The model assumes independence and cannot promise optimal plans.

Cold 100K/90% equality spent 814.54 ms building disposable postings before selecting Scan: 884.77 ms Auto median versus 79.46 ms forced Scan. Estimated execution work excludes that separately measured cold build. This overhead is published rather than hidden by changing the workload.

Peak cumulative process RSS reached 295,212 KiB across the qualification cases. RSS includes seeding, recovery, caches and caller results; allocations are unavailable, not modeled. The explicit benchmark bounds are 256 MiB logical index charge, 100,000 returned rows and 64 MiB returned bytes; product defaults remain 16 MiB, 4,096 rows and 2 MiB.

## Provenance and validation

Measured clean source: `dde442fe846891a2bb8f034a09cac467ec1ad88f`.
Source tree SHA-256: `138a3238c1d29e84978f5ed08867a32ec59544a8e4928b30635b592b5e1f4980`.
Benchmark executable SHA-256: `95974378f80590f8bb10dc926d324b9ece8a2ce2029f9eaeed695a8709557ef6`.
UTC: `2026-10-16T22:54:13.601398+00:00`; `rustc 1.99.1 (58cf8f9c3 2026-10-13)`; `Linux-6.18.44-x86_64-with-glibc2.41`; 5 available CPUs and 35,743,784,960 reported RAM bytes.

Local formatting, all-target/all-feature Clippy, full workspace recovery/correctness tests, Rust 1.89 compatibility, warning-free API docs and Rust/TypeScript HTTP compatibility suites pass. Tests include generated nested predicates, missing/null/numeric semantics, arbitrary byte ranges, invalid definitions, index budget failure, rebuild/reopen/checkpoint/compaction, subscription resume and a controlled adaptive restart while a fully installed writer waits to publish. Original public Rust structs are constructed/destructured externally to check source compatibility.

## Publication status

This is candidate documentation and measured evidence. No 0.8.2 binary download is claimed here. Matching clean-source native macOS/Linux package receipts and canonical website deployment remain release gates. Hosted CI currently fails before runner steps and a native macOS runner is unavailable in this Linux environment; no Sites deployment tool is available in this session. Existing qualified 0.8.0-preview.1 downloads remain available.

For source maintainers, reproduce with `python3 scripts/run-adaptive-bench.py target/new-adaptive-evidence` from an empty destination on a clean checkout. The runner checks source/HEAD stability and retains raw measurements. The database implementation remains private; this repository publishes documentation and evaluation assets only.
