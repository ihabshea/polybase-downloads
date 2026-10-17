# Polybase 0.8.2 adaptive execution qualification — 2026-10-16 UTC

[Complete raw report](results.json) contains every timed sample, EXPLAIN, configuration, and provenance field. All numbers below are measured; optimizer work units are kept separate from elapsed microseconds.

All **60 cases** passed complete-result Auto versus forced-Scan equality, strict byte-key ordering, and zero-duplicate checks. This comprises 1,560 measured query pairs, plus 180 warmup pairs. Each pair uses the same captured position. These are latency workloads without concurrent writers; the publication-race and recovery suites are separate correctness qualifications.

Both performance goals passed at 100,000 records:

- At 1% single-Eq selectivity, Auto measured **46.21×** faster than forced Scan (p50 1.156 ms versus 53.402 ms). This retains approximately **104.6%** of the historical 44.2× speedup, above the 80% / 35.36× goal. The historical baseline was a separate shared-host run, not a simultaneous comparison.
- At 90%, the planner chose **Scan initially**, with no adaptive restart. Auto p50 and forced-Scan p50 were effectively equal; the exact samples appear below.

The optimizer also has a measured counterexample: perfectly correlated AND predicates at 50% selectivity choose an intersection, restart, and run **1.58× slower** than starting with Scan at 100K. Cold optimization-cache builds remain expensive even when Scan is ultimately selected. These results are retained unchanged.

## Provenance and configuration

| Field | Actual value |
| --- | --- |
| Run started (UTC) | `2026-10-16T22:54:13.601398+00:00` |
| Source SHA | `dde442fe846891a2bb8f034a09cac467ec1ad88f` |
| Source dirty | `false` |
| Source-tree SHA-256, identical before/after | `138a3238c1d29e84978f5ed08867a32ec59544a8e4928b30635b592b5e1f4980` |
| Benchmark executable SHA-256 | `95974378f80590f8bb10dc926d324b9ece8a2ce2029f9eaeed695a8709557ef6` |
| Raw report SHA-256 | `b7617e427b109cebd2412c170e0d44600655419b3b428773ab95115cbdb95913` |
| Host | `Linux-6.18.44-x86_64-with-glibc2.41` |
| Rust | `rustc 1.99.1 (58cf8f9c3 2026-10-13)` |
| Profile / available CPUs | `release` / 5 |
| Physical RAM reported by host | 35,743,784,960 bytes (33.29 GiB) |
| Filesystem | Linux `overlay` at `/workspace` |
| Dataset sizes | 1,000 / 10,000 / 100,000 records |
| Actual result selectivities | 0.1% / 1% / 10% / 50% / 90% |
| Workload families | Single Eq, correlated AND, independent AND, independent OR |
| Samples | 5 cold Auto/Scan pairs; 3 warmup pairs; 21 warm Auto/Scan pairs per case |
| Query bounds | `records/` prefix; complete result; page size 100,000 |
| Limits | `max_keys = records + 3`; index 256 MiB; results 100,000 rows / 64 MiB |
| Calibration | Disabled; default process-local weights |
| Largest process peak RSS | 295,212 KiB (288.29 MiB) |
| Allocation counts | Not measured (`null` in raw report) |

Each case runs in a separate process. Peak RSS is cumulative Linux `VmHWM` for that process, including seed, recovery, repeated disposable-cache builds, and retained query results. It is neither a per-query allocation count nor a configured memory cap.

Cold means the database was reopened separately before each timed query, leaving the disposable optimization cache unbuilt. Database open/recovery itself is excluded from timing. OS/page caches are uncontrolled: these are **not disk-cold measurements**. Auto/Scan acquisition order alternates. Raw samples preserve acquisition order; p50 uses the median and p95 uses nearest rank. Five cold and 21 warm samples support local comparisons, not a production tail-latency guarantee.

## Reproduction and workload construction

From an authorized source checkout at the recorded SHA, with Cargo and the recorded Rust toolchain available:

```sh
python3 scripts/run-adaptive-bench.py target/adaptive-082-repeat
```

The destination must be empty. The runner builds the release example, records the actual executable hash and source SHA, writes each case as it finishes, and rejects a changed source digest or HEAD. Use the raw report to compare host/toolchain differences; the script does not pin CPU frequency or clear OS caches. The downloadable evaluation archive does not contain the private engine source or this native benchmark executable.

Single Eq uses the original `p01`/`p10`/`p90` document layout and three index definitions. At 1%, documents, byte keys, and definitions match the [0.8 baseline workload](../0.8.0-preview.1/results.json); only the queried `p01` distribution changes for other selectivities. AND/OR families use two boolean fields (`left`/`right`) and two definitions. Compare latency within a family, since payload and index counts differ between families.

Correlated AND sets both fields identically. Independent AND/OR construct exact target result cardinality with near-independent boolean marginals, then spread rows through key order using the coprime permutation `rank = (i * 237) % records`. Each raw case reports both marginals, observed joint intersection, and the independent joint expectation. Integer granularity prevents perfectly independent balanced OR marginals at 1K / 0.1%: its one-row union has one true row in each branch. That case is explicitly discrete and should not be interpreted as a general independence result.

## Warm paths at 100,000 records

Times are milliseconds, written **p50 / p95**. Speedup is forced-Scan p50 divided by Auto p50; values below 1 mean Auto is slower.

| Family | Result selectivity | Initial → final strategy | Auto ms p50 / p95 | Forced Scan ms p50 / p95 | Scan / Auto |
| --- | ---: | --- | ---: | ---: | ---: |
| Eq | 0.1% | Lookup | 0.220 / 0.326 | 52.529 / 55.528 | 239.20× |
| Eq | 1% | Lookup | 1.156 / 1.973 | 53.402 / 59.562 | 46.21× |
| Eq | 10% | Lookup | 10.007 / 12.357 | 48.224 / 50.519 | 4.82× |
| Eq | 50% | Scan | 55.087 / 71.323 | 53.789 / 58.874 | 0.98× |
| Eq | 90% | Scan | 55.402 / 59.549 | 55.606 / 64.826 | 1.00× |
| Correlated AND | 0.1% | Intersection | 0.149 / 0.206 | 35.480 / 39.898 | 238.00× |
| Correlated AND | 1% | Intersection | 0.968 / 1.893 | 45.282 / 47.334 | 46.77× |
| Correlated AND | 10% | Intersection | 7.487 / 9.265 | 42.477 / 44.249 | 5.67× |
| Correlated AND | 50% | Intersection → Scan | 71.726 / 75.991 | 45.458 / 48.169 | 0.63× |
| Correlated AND | 90% | Scan | 40.672 / 46.751 | 40.762 / 42.892 | 1.00× |
| Independent AND | 0.1% | Intersection | 0.702 / 0.947 | 44.846 / 46.795 | 63.91× |
| Independent AND | 1% | Intersection | 2.237 / 2.947 | 43.911 / 46.353 | 19.63× |
| Independent AND | 10% | Intersection | 12.117 / 17.003 | 45.224 / 51.588 | 3.73× |
| Independent AND | 50% | Intersection | 48.409 / 99.259 | 60.625 / 109.438 | 1.25× |
| Independent AND | 90% | Scan | 87.034 / 127.244 | 79.032 / 149.809 | 0.91× |
| Independent OR | 0.1% | Union | 0.282 / 0.438 | 63.233 / 113.827 | 224.63× |
| Independent OR | 1% | Union | 1.342 / 5.602 | 64.743 / 135.608 | 48.24× |
| Independent OR | 10% | Union | 24.720 / 28.564 | 130.245 / 144.329 | 5.27× |
| Independent OR | 50% | Union | 82.142 / 110.585 | 107.737 / 162.740 | 1.31× |
| Independent OR | 90% | Scan | 76.256 / 137.451 | 76.112 / 260.936 | 1.00× |

## Actual work and memory at 100,000 records

Canonical rows examined count both index lookups and any restarted full scan. Posting steps count consumed posting keys, including merge lookahead; they are not CPU comparisons. The forced Scan examines 100,000 canonical rows in every case. Raw EXPLAIN retains metadata and index-build counters; `total_rows_examined` also includes definition-coverage refresh rows.

| Family | Result selectivity | Matched rows | Canonical rows examined | Posting steps | Restarts | Process peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Eq | 0.1% | 100 | 100 | 100 | 0 | 265.07 |
| Eq | 1% | 1,000 | 1,000 | 1,000 | 0 | 265.00 |
| Eq | 10% | 10,000 | 10,000 | 10,000 | 0 | 265.42 |
| Eq | 50% | 50,000 | 100,000 | 0 | 0 | 275.14 |
| Eq | 90% | 90,000 | 100,000 | 0 | 0 | 288.29 |
| Correlated AND | 0.1% | 100 | 100 | 200 | 0 | 214.55 |
| Correlated AND | 1% | 1,000 | 1,000 | 2,000 | 0 | 214.48 |
| Correlated AND | 10% | 10,000 | 10,000 | 20,000 | 0 | 215.69 |
| Correlated AND | 50% | 50,000 | 136,459 | 72,918 | 1 | 224.82 |
| Correlated AND | 90% | 90,000 | 100,000 | 0 | 0 | 238.59 |
| Independent AND | 0.1% | 100 | 100 | 6,313 | 0 | 215.16 |
| Independent AND | 1% | 1,000 | 1,000 | 19,962 | 0 | 216.33 |
| Independent AND | 10% | 10,000 | 10,000 | 63,155 | 0 | 219.96 |
| Independent AND | 50% | 50,000 | 50,000 | 141,335 | 0 | 229.25 |
| Independent AND | 90% | 90,000 | 100,000 | 0 | 0 | 239.48 |
| Independent OR | 0.1% | 100 | 100 | 100 | 0 | 214.34 |
| Independent OR | 1% | 1,000 | 1,000 | 1,002 | 0 | 214.48 |
| Independent OR | 10% | 10,000 | 10,000 | 10,264 | 0 | 216.77 |
| Independent OR | 50% | 50,000 | 50,000 | 58,578 | 0 | 229.13 |
| Independent OR | 90% | 90,000 | 100,000 | 0 | 0 | 242.80 |

## Cold optimization-cache paths at 100,000 records

Times are milliseconds, **p50 / p95**. Index-build timings are measured phases inside cold Auto execution; they exclude the separate definition-coverage refresh and other planning overhead. Complete raw cold EXPLAINs include these additional costs.

| Family | Result selectivity | Cold Auto ms p50 / p95 | Cold forced Scan ms p50 / p95 | Index build ms p50 / p95 |
| --- | ---: | ---: | ---: | ---: |
| Eq | 0.1% | 840.610 / 1261.457 | 55.126 / 56.971 | 831.493 / 1250.027 |
| Eq | 1% | 819.999 / 899.135 | 55.085 / 60.590 | 809.282 / 888.722 |
| Eq | 10% | 783.759 / 912.938 | 53.666 / 58.351 | 760.970 / 889.594 |
| Eq | 50% | 892.274 / 1120.951 | 65.200 / 68.223 | 810.823 / 1053.904 |
| Eq | 90% | 884.771 / 1280.667 | 79.456 / 112.239 | 814.537 / 1143.552 |
| Correlated AND | 0.1% | 507.671 / 572.046 | 45.194 / 47.504 | 501.346 / 565.431 |
| Correlated AND | 1% | 648.537 / 682.579 | 56.998 / 64.319 | 640.103 / 672.680 |
| Correlated AND | 10% | 618.626 / 640.013 | 48.387 / 52.299 | 600.597 / 621.471 |
| Correlated AND | 50% | 605.019 / 676.309 | 59.384 / 61.847 | 513.360 / 592.494 |
| Correlated AND | 90% | 611.644 / 708.422 | 68.560 / 72.940 | 521.616 / 640.859 |
| Independent AND | 0.1% | 504.760 / 611.462 | 43.134 / 45.839 | 497.558 / 604.039 |
| Independent AND | 1% | 545.452 / 760.604 | 49.335 / 52.891 | 536.044 / 750.639 |
| Independent AND | 10% | 612.317 / 746.589 | 47.425 / 50.177 | 593.121 / 724.748 |
| Independent AND | 50% | 769.058 / 814.652 | 71.691 / 93.222 | 716.634 / 762.323 |
| Independent AND | 90% | 989.661 / 1550.927 | 142.860 / 191.317 | 920.232 / 1317.249 |
| Independent OR | 0.1% | 1300.893 / 1611.950 | 97.302 / 118.164 | 1264.438 / 1597.905 |
| Independent OR | 1% | 957.779 / 1020.420 | 71.182 / 130.344 | 937.033 / 1007.043 |
| Independent OR | 10% | 1102.764 / 1365.552 | 104.887 / 241.321 | 1065.155 / 1335.848 |
| Independent OR | 50% | 1163.178 / 1669.877 | 88.382 / 192.834 | 1084.511 / 1545.664 |
| Independent OR | 90% | 1158.778 / 1632.500 | 69.024 / 199.568 | 1056.346 / 1451.208 |

## Counterexamples and limitations

1. **Correlation defeats the independence estimate.** At 100K / correlated AND / 50%, the planner estimates intersection work at 350,000 abstract units versus 700,000 Scan units. Actual execution reaches 36,459 canonical lookups and 72,918 posting steps, restarts once, and then scans all 100,000 rows. Auto measures 71.726 ms p50 versus Scan 45.458 ms: **1.578× slower**, while preserving all 50,000 ordered rows. The same unchanged workload loses at 1K and 10K: 1.500× and 1.505× slower, respectively. These are the only warm cases where an initially indexed plan is slower than forced Scan in this run.
2. **Cold Scan selection still pays to build statistics/postings.** At 100K / single Eq / 90%, cold Auto measures 884.771 ms p50 versus cold forced Scan 79.456 ms; index build alone measures 814.537 ms. The final plan is correctly Scan, but discovering selectivity requires the disposable cache. Warm execution avoids the build. Estimated plan work describes execution, not this measured build latency.
3. **Planning and host variation affect equivalent scans.** Metadata/statistics planning adds work; for example, 100K / single Eq / 50% has a Scan/Auto p50 ratio of 0.976. The 100K / independent AND / 90% case has a ratio of 0.908 and broad p95 values on both paths. These measurements do not isolate planning overhead from shared-host variation. Costs are abstract work units, not fitted microsecond predictions.
4. **Scope is bounded local qualification.** Data is deterministic synthetic JSON. No concurrent writers, hardware power failures, allocator instrumentation, disk-cold guarantee, CPU isolation, or production tail-latency claim is made by these timings. Pagination continuations, publication races, recovery faults, clients, and optional calibration require their separate acceptance tests. Historical measured 0.8 speedup comparisons remain sensitive to shared-host and run-to-run effects.

The full report retains all 60 cases and both successful performance targets, including every slower result. No cases or samples were removed to improve the reported outcome.
