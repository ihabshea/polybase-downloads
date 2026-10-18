# Polybase 0.9 — measured Janus historical qualification

All **36 historical cases** passed complete ordered key/value byte comparison with a simple reference model and forced Scan. The concurrent phases passed **93 historical reads alongside a writer making 24 atomic commits**. All 27 historical cases with provisional warm p95 goals met those goals; whole-word text has no latency target.

**Seven of 12 current-head cases missed the 10% regression goal.** Every miss and every sample is retained below. Cold historical generation construction reached **1.996457 seconds p95** at 100K records. These measurements establish the tested behavior on this shared host; they do not claim production tail latency, isolated hardware or power-loss durability.

[Complete measured report](results.json) · [Fixed configuration](configuration.json) · [Before/after provenance](source-provenance.json) · [0.8.2 baseline provenance](baseline-provenance.json) · [Hardware](hardware.json) · [Rejected first run](rejected-first-run/INVALIDATED.json)

## Provenance

| Field | Actual value |
| --- | --- |
| Measurement interval (UTC) | `2026-10-18T12:29:24.278740+00:00` to `2026-10-18T12:32:16.532447+00:00` |
| Measured source SHA | `6a123302edad0ed49cac541615b9719bb007d188` |
| Source dirty | `false` |
| Source-tree SHA-256, equal before and after | `bf9d6fac9088c0546b9f1934318da38828eb8521e113f9d7b4ded3db4d8e2f28` |
| Janus benchmark executable SHA-256 | `d3fd4148aacff9e22de17651d569fd9fc7becace1f82769cc27da1b17a899f6c` |
| Complete report SHA-256 | `6c762f119fc62de8cfd5b2f0bd007574307e0b71fef95cb28189e0c7d062c605` |
| 0.8.2 baseline source SHA | `ce4daf3db59b570895022b136ebdfbae1665ffec` |
| Baseline engine Git tree | `70747bd5f8cd596e794c619c79c470a09a95976a` |
| Baseline executable SHA-256 | `5b3d6ab016ac7c4907331dfe28d9ec3272989a13bb155bda9965388c5c3526a1` |
| Compiler / profile | `rustc 1.99.1 (58cf8f9c3 2026-10-13)` / `release` |
| Extra compiler flags | `RUSTFLAGS` and `CARGO_ENCODED_RUSTFLAGS` unset |
| Host | `Linux-6.18.55-x86_64-with-glibc2.41` |
| CPU | `INTEL(R) XEON(R) PLATINUM 8573C`; inherited affinity CPUs 0–4 |
| RAM reported by host | 35,743,760,384 bytes |
| Filesystem | Linux `overlay` at `/workspace` |

The baseline is the unchanged 0.8.2 engine extracted with `git archive` at its recorded SHA. Only the current-head benchmark example and shared workload helper are added to that isolated source archive. Both recorded harness hashes and the executable hash are checked before reuse. The baseline and Janus executables use the same compiler, release profile, data generator, history depth and current-head `query_page`/`search` calls.

The source fingerprint includes code and configuration under `crates`, `clients` and `scripts`, including generated TypeScript declarations/JavaScript when present. Documentation added after this run does not change the measured engine source. The measured SHA remains explicit even when later documentation commits exist.

## Fixed workload and reproduction

From an authorized source checkout at the recorded SHA, with the recorded Rust compiler, Python 3.12 and Git available:

```sh
python3 scripts/run-historical-bench.py target/janus-09-repeat
```

The output destination must be empty. The runner builds the release example and either verifies the saved baseline or rebuilds it from the recorded old commit. It writes source provenance before building, preserves each completed dataset, and rejects a changed source fingerprint or HEAD. The benchmark example and engine source are private; the downloadable evaluation archive does not include this source harness or its benchmark executable.

- Record counts: 1,000, 10,000 and 100,000 JSON documents, plus one ordinary index-definition record.
- Seed documents in 512-record batches, create the `group` index and compact through that exact seed position. Retain 128 subsequent commits, each updating 16 keys. No history depth or limit is changed after measuring.
- Keys are `records/{i:06}`. Initially `group = i % 100`, `revision = 0`, and text is `janus amber history` for group 1 or `janus slate history` otherwise. Revision `r` updates keys `((r-1)*16 + offset) % records`, sets `group = (i+r) % 100`, and records that revision.
- Query the retained base, base+64 and base+127; the captured head is base+128. JSON equality selects typed `group == 1` (approximately 1%); text requires both whole words `amber history`. The point key is `records/{floor(records/3):06}`. The narrow range contains the next 64 byte-ordered keys starting there.
- Historical cache and scoped replay limits stay at their defaults: 64 MiB each, at most 200,000 retained versions. Derived posting budget is explicitly 256 MiB; results allow 100,000 rows / 64 MiB; WAL budget is 256 MiB; maximum live keys are record count+1.
- Each of 36 historical cases records five cold samples, three warmups and 31 warm samples. Cold means reopen with an empty disposable historical cache; open/recovery is excluded. Timers include `as_of` capture and execution; serialization and reference assertions run afterward. OS/page caches are uncontrolled, so cold does not mean disk-cold.
- The simple oracle computes each key's last revision at S independently, then compares the complete ordered returned key/value bytes on every cold/warm execution and one forced-Scan execution per case. Point reads are also compared with the forced range-query path.
- Current-head comparison records 31 alternating old/new sample pairs per workload and size, after three warmups. Only one process executes a measured query at a time; IPC, result hashing and JSON output are outside timers. Pair parity checks position, row count and framed ordered result CRC; historical cases separately compare every byte with the model.
- p50 is the median; p95 is nearest rank. Raw samples preserve acquisition order. Performance targets are goals, with no samples removed or replaced by modeled work units.

| Records | Retained base | Historical positions S | Captured head | JSON matches at the three S values |
| ---: | ---: | --- | ---: | --- |
| 1,000 | 3 | 3, 67, 130 | 131 | 10, 9, 11 |
| 10,000 | 21 | 21, 85, 148 | 149 | 100, 99, 100 |
| 100,000 | 197 | 197, 261, 324 | 325 | 1000, 999, 1000 |

## Historical latency

Times are measured milliseconds. The table shows the maximum p95 across the three retained positions for each fixed dataset and workload. All individual p50/p95 values, raw samples, positions and EXPLAIN counters remain in the linked reports. Warm historical point and JSON/text queries used the versioned in-memory lookup/postings; narrow ranges used a range scan. Cold requests honestly report historical replay and build work.

| Records | Workload | Worst warm p95 ms | Worst cold p95 ms | Warm target ms |
| ---: | --- | ---: | ---: | ---: |
| 1,000 | point | 0.000801 | 28.971588 | 10 |
| 1,000 | json_equality | 0.049136 | 41.944880 | 50 |
| 1,000 | narrow_range | 0.027838 | 31.700431 | 30 |
| 1,000 | text | 0.035591 | 26.757748 | — |
| 10,000 | point | 0.000552 | 134.503781 | 10 |
| 10,000 | json_equality | 0.101758 | 132.734087 | 50 |
| 10,000 | narrow_range | 0.010423 | 168.073338 | 30 |
| 10,000 | text | 0.157861 | 131.288518 | — |
| 100,000 | point | 0.000647 | 1638.677851 | 10 |
| 100,000 | json_equality | 3.635778 | 1556.999505 | 50 |
| 100,000 | narrow_range | 0.009280 | 1996.456601 | 30 |
| 100,000 | text | 0.964940 | 1695.718056 | — |

The cold bottleneck is building the complete verified historical generation and derived postings even for a point query. At 100K, the generation contains 102,049 versions including metadata, with 13,462,670 logically charged cache bytes and 124,480,794 posting bytes. These are logical charges, not allocator/RSS measurements. Warm reads reuse the generation and select canonical values at the exact requested position. Historical candidate postings cover retained versions and may include extra keys, which execution rechecks against canonical values at S.

| Records | Cumulative process peak RSS KiB | MiB |
| ---: | ---: | ---: |
| 1,000 | 7,052 | 6.89 |
| 10,000 | 24,484 | 23.91 |
| 100,000 | 200,524 | 195.82 |

RSS is Linux `VmHWM` for the entire per-dataset historical process, including seed, recovery, repeated cache construction, reference values and result buffers. It is not per-query memory and is not the configured logical cache limit. Allocations were not measured (`null` in raw cases).

## All seven current-head target misses

The goal is new/baseline ≤1.10 for **both p50 and p95**. Values below are measured milliseconds, with ratios computed from the unrounded raw samples. No workload was changed after seeing these misses. All 12 cases, including the five that met this goal, are retained in `current-*.json` and the complete report.

| Records | Workload | 0.8.2 p50 / p95 ms | 0.9 p50 / p95 ms | New/old p50 | New/old p95 |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1,000 | narrow_range | 0.012924 / 0.015262 | 0.014847 / 0.028765 | 1.149× | 1.885× |
| 1,000 | text | 0.009967 / 0.010463 | 0.010093 / 0.013598 | 1.013× | 1.300× |
| 10,000 | point | 0.003621 / 0.003882 | 0.004591 / 0.004793 | 1.268× | 1.235× |
| 10,000 | json_equality | 0.081324 / 0.098003 | 0.126398 / 0.151160 | 1.554× | 1.542× |
| 10,000 | narrow_range | 0.010313 / 0.011563 | 0.013302 / 0.014043 | 1.290× | 1.214× |
| 10,000 | text | 0.066146 / 0.086877 | 0.095069 / 0.139513 | 1.437× | 1.606× |
| 100,000 | json_equality | 1.195508 / 1.499605 | 1.152107 / 3.129816 | 0.964× | 2.087× |

At 100K, JSON p50 improved from 1.195508 to 1.152107 ms, while p95 increased from 1.499605 to 3.129816 ms; that remains a target miss. Small-query absolute timings are also shown because ratio changes of a few microseconds can be large. The host is shared, with inherited affinity and no per-process CPU pinning or frequency control. These timings do not isolate a code-change effect from scheduling/cache/frequency variation. The different miss pattern in the rejected first run is retained as evidence of run-to-run sensitivity, not used to select a favorable result.

## Concurrent reads and preservation of the first attempt

For each dataset, 31 reads at base+64 start alongside a writer making eight 16-key commits. All 93 reads equal the retained reference state and all 24 commits complete atomically. A single start barrier permits scheduler-controlled overlap; controlled publication-boundary and crash/recovery tests provide the separate adversarial evidence. The benchmark does not claim every read overlapped a publication.

The [first complete run](rejected-first-run/rejected-run.json) is explicitly **unqualified**. Its source HEAD stayed `3a0067c68a81978075bf5decc94e35822f9b18e3`, but ignored TypeScript `dist/client.js` and `dist/client.d.ts` were regenerated at 12:22:36 UTC during the measurement. The source fingerprint changed, so the runner rejected qualification. All 36 historical cases, 12 current cases, raw samples and all four observed small-workload misses remain in [rejected-first-run](rejected-first-run/INVALIDATED.json). Original before/after fingerprint values were not written by that runner version and remain explicitly `null`; they are not reconstructed or invented.

Before this final complete repeat, a diagnostics-only current-search cache-hit report was corrected and source fingerprint persistence was added. The workload, target checks, sample counts, history depth and limits stayed identical. The final run used the clean source SHA and equal before/after hashes recorded above; neither the invalidated attempt nor any of its misses is represented as final qualification.

This is benchmark evidence for the measured private source. It does not assert that matching native Mac/Linux packages or website publication have completed. Retention, corruption, recovery, API compatibility and crash qualification remain explicit release gates with their own artifacts.
