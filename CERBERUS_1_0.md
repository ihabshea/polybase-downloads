# Project Cerberus — 1.0.x candidate

Cerberus challenges the database's atomic commit, recovery and retained-history contracts under process termination, independent file damage and overlapping maintenance. A successful test is evidence for its recorded workload and machine. The candidate is not a published 1.0 release.

The published database remains 0.9.0 and published SDKs remain 0.8.3. [Download the current evaluation](https://base.polymathlabs.xyz/download.html) or read [the Janus historical query contract](https://base.polymathlabs.xyz/janus-0-9.html). No new storage or WAL format is introduced by this challenge.

## Mission

Three guardians check one committed history. Crash tests terminate a real process at named durability boundaries and inspect recovery. Ordering tests search a simple sequential reference model for a real-time-compatible explanation of completed concurrent transactions. Historical tests compare every retained commit position with an independent reference.

| Acceptance workload | Challenge target | Recorded result |
| --- | --- | --- |
| Generated concurrent histories | 10,000 | 10,000 checked, with 220,000 recorded operations |
| Real injected process terminations | 1,000 or more | 1,056 primary cases and 1,116 actual SIGKILL deaths |
| Reference-model mismatches | Zero | Zero; also zero inconclusive or invalid histories |
| Silent corruption in the stated damage scope | Zero | Zero across 1,000 covered damage cases |

The challenge thresholds are now distinguished from the completed recorded campaign. All 33 required named engine boundaries were covered; 180 publication kills had concurrent maintenance pending. The extra-credit client run passed 64 equivalent Rust/Node histories, making 70,016 SDK calls and 5,376 historical-position checks through candidate SDK 0.9.0 sources. This does not claim that those candidate SDKs are published; registry availability remains 0.8.3.

## Recorded qualification

The complete campaign passed on clean source `54c92946abbaea30bae25e2e8178676e17cbd9e8`. Its before/after source fingerprint is `59414ad073b25ef09fe956f73a0b134eeb5a520e9eed07f2004f19590b076765`. The [raw campaign report](qualification/1.0.0/results.json) has SHA-256 `9a5f77681901c25f460c2c878a28a4cf803451006a2538cd63716a75cc0b83dc` and records exact executable hashes, configuration, stages and scope.

The recorded host was native x86-64 Linux with glibc 2.41, Rust/Cargo 1.99.1, Node 24.19.0 and Python 3.12.14, with five available CPUs. These are correctness results for the recorded workloads, not performance claims or proof of every possible execution.

Historical integrity checks made 242,364 cumulative retained-position audits across histories and phases, with 5,816,736 quiescent historical queries and 160,000 concurrent historical observations. Historical read intervals overlapped acknowledged write calls 100,047 times and maintenance calls 78,322 times. Termination receipts add 18,900 retained-position checks. No acknowledged commit loss or partial batch was observed in scope.

The covered corruption outcomes were 875 strict rejections without repair, 100 recoveries preserving a verified boundary and 25 recoveries of a complete unacknowledged commit. Their 7,381 historical-position checks include pristine reference preflight and post-recovery audits when recovery succeeds; rejected damaged fixtures expose no query results. The separate valid-CRC forgery control was accepted, demonstrating the non-authentication limit; it is excluded from these passing counts.

The public [independent Python witness report](qualification/1.0.0/independent-witness-validation.json) validates all 10,000 supplied witnesses, 220,000 recorded operations and 40,000 stored visible-head/event observations. It runs no engine and performs no alternative-order search. It does not recheck historical predicates or unstored live responses. It independently validates supplied serial witnesses rather than proving the absence of a witness.

## Deterministic crash boundaries

Named failpoints cover WAL append, synchronization, durable frontier selection, commit publication, checkpoint creation, snapshot installation and compaction. A test process reports reaching its selected boundary before the parent sends SIGKILL. Recovery reopens the same directory and checks the allowed complete committed prefix. A scheduled case, a reached boundary and an actual termination are distinct counts.

An acknowledged durable commit must remain present. A prepare-only or partially written transaction cannot become a partial batch. An unacknowledged call may have committed completely; a lost acknowledgment is not a definite abort. Recovery must preserve that distinction.

## A serial explanation

The reference model is deliberately small: a byte-key BTreeMap, whole atomic mutations and independently evaluated observations. Each recorded transaction has an invocation tick, response tick, observed point/range reads, staged mutations and an outcome. Successful read-only transactions validate a prefix without allocating a commit. Even a same-value put or absent-key delete is a write event.

The checker searches possible serial orders while respecting completed-before-invoked relations. It validates observations, read-your-writes behavior, atomic effects and receipt positions at each candidate step. It does not turn the engine's commit-position order into an assumed proof. Definite conflict/abort outcomes are no-ops; their provisional reads do not become committed observations. Unknown engine outcomes are inconclusive and fail qualification.

The search is bounded to at most 64 completed operations with 64 steps each. Default limits admit 100,000 search states, 8 MiB of logical input and a 256 KiB/1,024-row reference state. A limit or invalid trace never counts as a successful check or a proved mismatch. Passing generated histories do not constitute exhaustive model checking or a formal linearizability proof.

## Retained history

For every retained commit position, point reads, byte-key ranges, typed JSON predicates and whole-word text queries must match the reference's complete transaction state. Checks interleave history reads with writes and maintenance, then repeat after checkpoint, compaction and reopen. Expired positions remain explicit errors rather than valid empty results.

Typed JSON equality preserves the existing numeric equivalence of `1` and `1.0`, with distinct missing and null semantics. Legacy scalar search retains its exact scalar encoding. Byte-key ordering and zero duplicates remain part of the comparison. The [Janus contract](https://base.polymathlabs.xyz/janus-0-9.html) describes the bounded cache, replay and captured-generation strategy.

## Independent corruption

The qualifying corruption scope is independent byte and structural damage to WAL records, snapshot data and metadata. A case must reject invalid state or recover only from a demonstrably valid durable boundary. The test compares acknowledged state and historical observations after recovery. It never accepts a silent repair that invents committed data.

CRC checksums are integrity checks, not authentication. A checksum-preserving coherent forgery is outside this threat model. A separate negative control demonstrates that limitation and does not contribute to the detected-corruption or passing-case totals. Coherent rollback or replacement of the entire database directory is also outside the documented guarantee.

## Replay a failure

Each failure artifact records its random seed, operation history, failure point, engine version, source/executable identity and replay command. The original observed history remains intact. The replay command can recheck that recorded trace deterministically; a separate engine workload replay exercises the generated intent again.

Transaction observations, concurrent historical responses and visible head/event payloads are archived in the recorded trace. Successful quiescent all-position responses were compared live, with per-phase counters retained; their complete payloads are not all archived. Offline Rust trace replay therefore checks the stored responses, not every live historical query again. The independent Python validator has the narrower witness/head/event scope stated above.

The random seed determines generated operations, not an arbitrary OS thread schedule. Real invocation/response ticks and observed results are therefore retained. A pure trace replay proves or rejects the same serial-history claim without pretending to recreate an unrecorded kernel interleaving.

Observed-trace reduction keeps every acknowledged mutator and every mutation as context. Deleting those could manufacture a missing producer or a receipt-position gap. Only whole read-only/aborted operations and whole read/expect observations may be removed. Returned bytes, positions and intervals are never fabricated. A final single-deletion audit establishes context-preserving 1-minimality within those permitted deletions, not a globally shortest workload. A reduction budget failure explicitly prevents a minimality claim.

The complete qualification runner requires a clean, unchanged private source checkout, Rust 1.89 or later, Node 24 or later, Python 3.11 or later, a supported local POSIX filesystem and a new empty evidence directory. Use the recorded Rust 1.99.1 toolchain and source for matching build provenance:

```sh
python3 scripts/run-cerberus.py target/NEW-cerberus-evidence \
  --seed 20261025 --histories 10000 --operations 12 --threads 3 \
  --terminations 1056 --corruptions 1000 --client-seeds 64 --client-mutations 8
```

This command reproduces the recorded campaign configuration. The passing evidence is the separately linked report, not the command itself. The runner retains exact source and executable hashes, actual case receipts, stage logs and the recorded response traces. A development run with `--smoke` is explicitly ineligible for qualification.

```sh
target/release/examples/cerberus_verify --replay-history FAILURE.json
target/release/examples/cerberus_verify --replay-workload FAILURE.json --output NEW_EMPTY_DIRECTORY
target/release/examples/cerberus_verify --check-traces histories.jsonl
```

## Release blockers

Within the supported process-termination and independent-damage scope, any acknowledged durable commit disappearing after restart blocks release. Any uncommitted partial batch becoming visible blocks release. Any historical query returning the wrong retained version blocks release. Inconclusive checks and incomplete campaigns cannot be used to meet the acceptance thresholds.

## Limits

SIGKILL tests process termination, not sudden hardware power loss. Filesystem synchronization and atomic rename assumptions remain unchanged. The suite does not certify every storage device, filesystem or scheduler interleaving. Corruption checks do not provide cryptographic authenticity.

The database engine remains private. Only synthetic evidence, public client code and operational qualification recipes may be published. Native package and registry availability are separate publication checks. A candidate page, a local binary and an unexecuted target are not a released download. Hosted SaaS is coming soon.
