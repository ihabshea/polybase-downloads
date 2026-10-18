# Project Janus 0.9.0 deterministic verification

Measured on 2026-10-18T12:28:26.141273+00:00 from clean, unchanged source
`6a123302edad0ed49cac541615b9719bb007d188` with rustc 1.99.1 (58cf8f9c3 2026-10-13), Python 3.12.14,
and Linux-6.18.55-x86_64-with-glibc2.41. These are correctness and recovery receipts, separate from
performance measurements and native package qualification.

The complete run passed: eight seeds (`20261018` through `20261025`), **1,600
operations**, **836 historical checks**, **11 expired-page-cursor checks**, and
**37 injected process-crash scenarios** (seven commit, six named-request, twenty
checkpoint/compaction, four recovery-selection/cleanup). The fault integration
suite reports six passing tests, including its reducer self-test and replay entry
point. `correctness_passed` and `verification_gate_verified` are both `true`.

Each generated operation is checked against a simple BTreeMap reference with a
snapshot per committed transaction. Checks cover visible state, ordered raw
events, overlapping transactions, expected-value conflicts, ABA, named retries
after a discarded acknowledgment and reopen, checkpoints, compaction, historical
point/JSON/text/range results, forced-scan parity, historical pagination, and
subscription resume deltas. Historical explains are checked against the exact
position, returned row count and returned bytes. The 836 historical checks include
valid, future and expired positions; they are not 836 successful result queries.

| Artifact | SHA256 |
| --- | --- |
| Source inputs, identical before/after | `bf9d6fac9088c0546b9f1934318da38828eb8521e113f9d7b4ded3db4d8e2f28` |
| `janus_verify` measured executable | `5a312368907aefb8e6f297c52315a794afa1e22ef4dfc877830ca11583eb2c46` |
| `polybase-fault` measured executable | `ba95ce1f6d03c9a04cfcfb2b663a4344c1d4acf466bec42bb8f79a40d0ccfc7a` |
| `results.json` | `010fe595a83d6059d1656159075ed8bbd7fb6864e014f91bd8cefdbe81b221f3` |

The directory contains the unchanged combined `results.json`, eight individual
seed reports, all 37 synthetic fault receipts and the actual fault-test log.
`SHA256SUMS` covers every receipt, log and this README. No engine implementation
or executable is included in this evidence bundle.

From an authorized source checkout at the exact source SHA above, with Cargo and
Python available, reproduce into a new empty destination:

```sh
python3 scripts/run-janus-verify.py target/janus-verify-reproduced --seed 20261018 --seeds 8 --operations 200
```

The runner builds the release harness, records its executable hash, runs all seeds
and the crash suite, checks all 37 receipts, and rejects source changes during the
run. Timing and local build paths in a new report can differ. The synthetic
operation history and externally observable results must agree.

On a mismatch the harness records the seed, engine version, source SHA, original
operations, minimized operations, failure category and replay command. It replays
candidate reductions in fresh directories, applies delta debugging, then deletes
individual operations to a fixed point while preserving the failure category.
This gives a **1-minimal deletion workload**, not a proof of the globally shortest
workload. It does not minimize arbitrary byte values or thread schedules. If a
failure does not reproduce during final reduction verification, the report says
so and preserves the original history. No mismatch occurred in this run.

A generated saved mismatch can be replayed with:

```sh
cargo run --release --locked -p polybase-engine --example janus_verify -- --replay /path/to/failure-seed.json
POLYBASE_JANUS_FAULT_REPLAY=/path/to/fault-failure.json cargo test --release --locked -p polybase-cli --all-features --test janus_faults replay_saved_fault_workload -- --exact --nocapture
```

The crash-suite reducer also removes individual setup mutations while preserving
the observed failure category. These are bounded seeded workloads and SIGKILL
process faults on one local Linux environment. They do not prove exhaustive
interleaving coverage, hardware power-loss behavior, macOS package readiness or
all release gates.
