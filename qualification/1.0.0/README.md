# Project Cerberus — measured 1.0.0 qualification

The agreed process-crash and independent byte/structural-corruption matrix passes
on the recorded Linux host. This is engineering qualification for a candidate,
not a claim that a 1.0 download or website deployment has been published. The
current public database remains 0.9.0 and registry clients remain 0.8.3.

| Acceptance workload | Actual result |
| --- | ---: |
| Distinct seeded concurrent histories | 10,000 |
| Recorded operations with serial witnesses | 220,000 |
| Primary termination/restart cases | 1,056 |
| Actual observed SIGKILL exits | 1,116 |
| Independent covered damage cases | 1,000 |
| In-scope model mismatches / inconclusive checks / silent corruption | 0 / 0 / 0 |
| Same-program Rust/Node trials | 64 |
| Actual SDK calls across both clients | 70,016 |

The [exact campaign report](results.json) is SHA-256
`9a5f77681901c25f460c2c878a28a4cf803451006a2538cd63716a75cc0b83dc`.
Clean source was `54c92946abbaea30bae25e2e8178676e17cbd9e8`; its before/after
source fingerprint was
`59414ad073b25ef09fe956f73a0b134eeb5a520e9eed07f2004f19590b076765`.
All six actual executable identities stayed unchanged. Hardware, toolchains,
configuration, elapsed stage times, commands and output hashes are in the report.

## What was checked

The bounded Rust checker searches real-time-compatible serial orders; it does not
assume that sorting engine receipts proves correctness. It checked read sets,
read-your-writes, expectations, atomic mutations, positions and available `wrote`
flags. Definite aborts are no-ops with provisional reads. Unknown outcomes,
invalid traces and exhausted checker budgets fail the gate.

Live historical checking covered 242,364 retained-position audits across
maintenance/reopen/expiry phases and 5,816,736 complete quiescent query calls,
including forced Scan, point and byte-range reads, typed numeric/null/missing/
nested JSON and whole-word/Unicode text. Another 160,000 historical queries ran
with concurrent writers and maintenance. Actual API intervals recorded 100,047
historical calls overlapping a successful write and 78,322 overlapping
maintenance. Counts are cumulative audits, not distinct databases or positions.

The [33 named failpoints](failpoint-inventory.json) form 86 operation/boundary
combinations. Each primary case reached its selected rendezvous before a real
SIGKILL. Sixty additional setup terminations account for the difference between
1,056 cases and 1,116 kills. Recovery checked 18,900 exact retained prefixes,
complete atomic state, raw events, cursors and retries. In 180 publication kills,
observed worker-start markers confirmed checkpoint/snapshot callers had been
invoked while publication was paused; acknowledgment-only cases are excluded
from that overlap count.

Forty damage modes each ran 25 seeded cases: 875 invalid fixtures were rejected
without selected-file repair, 100 recovered a verified existing boundary and 25
recovered a complete unacknowledged commit. Corruption position-check counts
include pristine reference preflight plus checks after successful recovery;
rejected fixtures expose no query result. A complete unacknowledged commit is an
allowed uncertain outcome, not a partial batch or an invented acknowledgment.

The [client report](clients/results.json) compares actual repository Rust and Node
SDKs (source version 0.9.0) against an independent model, not just against each
other. It records 5,376 historical-position checks. Opaque database identities,
timing and planner choices are normalized. Legacy scalar queries use integer
`1`, because JS serialization cannot preserve a `1.0` query lexeme; stored raw
`1.0` and typed numeric equivalence remain tested. Discarded client acknowledgments
are application-level discards; actual process-kill outcomes belong to the
separate termination campaign. These source SDKs are not a new registry release.

## Independent witness validation

An independent standard-library Python implementation validated all 10,000
supplied witnesses, 220,000 operations and 40,000 stored full-head/event
observations. It invokes neither the engine nor the Rust checker. See the
[actual validation report](independent-witness-validation.json) and
[tool scope and controls](tools/LINEARIZABILITY_WITNESS.md).

```sh
python3 -B tools/verify-linearizability-traces.py histories/histories.jsonl.gz \
  --expected-sha 54c92946abbaea30bae25e2e8178676e17cbd9e8 \
  --expected-version 1.0.0 --expected-count 10000 \
  --expected-first-seed 20261025 --report NEW-witness-report.json
python3 -B tools/test-linearizability-witness.py
```

This validates the supplied witness and stored head/events, not the absence of a
witness, authentication of the recorder, historical predicates, or responses
that were not archived. The Rust trace replay additionally rechecks its stored
concurrent/historical observations. Successful exhaustive quiescent responses
were checked live and retained as phase counts, rather than all copied into the
trace. Failed observations are retained with the failure artifact.

## Evidence layout and replay

The 24,296,188-byte gzip stream preserves the exact 485,334,174-byte JSONL trace.
Stream it directly to avoid materializing the uncompressed file. Its decompressed
SHA-256 is
`b52c4be9b2af6f03a572d3022e65ec00a5b5591a5b70fc2249541c22f99a6d07`.
`termination-receipts.tar.gz`, `corruption-receipts.tar.gz` and
`client-programs.tar.gz` contain 1,056, 1,000 and 64 exact original JSON members.
Extracting them restores their original relative paths. [Archive identities](archive-layout.json),
the original run manifest and final checksums distinguish compression from
discarding evidence. Build/test and phase stdout/stderr logs are retained.

Full engine reproduction requires the private engine checkout, Rust, Node 24,
Python 3.11+ and supported local Unix filesystem/signal behavior. In the managed
environment, activate `/workspace/polybase-env.sh` first. Use a new empty output:

```sh
python3 scripts/run-cerberus.py target/NEW-cerberus \
  --seed 20261025 --histories 10000 --terminations 1056 \
  --corruptions 1000 --client-seeds 64
```

The runner records source and binary hashes and rejects a changed checkout.
Smoke runs never qualify. Seeds reproduce generated intent, not arbitrary OS
thread scheduling. Recorded-trace replay is deterministic. Failure reducers
preserve committed producer context or minimize fresh valid physical/program
fixtures, and explicitly state budgets and context-preserving 1-minimality rather
than promising a globally shortest failure.

## Agreed limits and publication

SIGKILL preserves the OS page cache; these tests do not simulate hardware power
loss or dishonest synchronization. Passing bounded histories is not a formal
proof of all schedules, fairness or every possible workload.

CRCs do not authenticate storage. The separate
[checksum-forgery negative control](corruption-receipts/negative-controls/valid-crc-preserving-wal-forgery.json)
demonstrates an accepted earlier WAL rewrite with recomputed checksums, unchanged
head and metadata, and a changed old historical value. **It is excluded from the
passing damage count and the in-scope zero-mismatch/silent-corruption claims.**
This limitation was explicitly selected in the challenge scope before the final
campaign. CRC collisions and coherent directory rollback are likewise excluded.

Production-default code has no armed rendezvous callbacks; the test feature does
not change persistent formats or existing observer enums. Native downloadable
1.0 artifacts and website deployment remain separate publication requirements.
No engine/server implementation or user database is included in this public
proof bundle; all data is synthetic. The Python witness validator is an
independent verification tool.
