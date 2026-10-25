# Project Atlas — 1.5 release contract

**Draft 1 · October 25, 2026. Engineering candidate, not a qualified release.**

Atlas carries the existing single-partition, three-voter replication architecture
across machines, elections, voter replacement and operational lifecycle changes.
The public database download is 1.0.0. See the [availability correction](qualification/atlas/AVAILABILITY_ERRATUM.md) for stale copy preserved in immutable snapshots. Cerberus's local fault campaign is
evidence for a node; it does not qualify a distributed cluster.

The measured candidate `b2c865f0c8299e7f54784d81d012d35aa7b79512` completed
50,000 local same-process histories and a separate 1,000 overlay-backed histories,
independently rechecked with no recorded reference mismatch or inconclusive pass.
The repeated paired benchmark passed **11/12 current-head** and **36/36 cold-history**
targets. The 1K range p95 remains 1.156× baseline, above the unchanged 1.10× gate.
All first-iteration counterexamples remain preserved. Neither the three-host nor
performance release gate is closed. See the [performance report](ATLAS_PERFORMANCE.md).

## Release gates

| Required property | Acceptance evidence |
| --- | --- |
| Acknowledged quorum commits survive | No lost success after elections, partitions, restart or supported replacement |
| Atomicity | No partially visible multi-key transaction |
| One committed history | No conflicting committed prefixes or split-brain acknowledgments |
| Retained history | Exact point, byte-range, typed JSON and whole-word results at the requested cluster position |
| Elections and transfer | Interrupted elections and snapshot transfer preserve verified state |
| Moving quorums | Learner staging, joint voting and final three-voter configuration survive faults/restart |
| Continuous operations | Specifically supported rolling version pairs pass follower-first replacement and leader handover |
| Independent checking | 50,000 generated histories; independent real-time-compatible witnesses; no inconclusive-as-pass |
| Cross-host provenance | 10,000 actual network/process schedules across three independent hosts/VMs and at least three seeded profiles |
| Performance | All fixed baseline gates pass repeated paired measurements, with raw misses retained |

The [acceptance tracker](ATLAS_1_5_TRACKER.md) separates implemented APIs, locally
tested observations and full release qualification. A local scheduler, three
processes or three containers cannot substitute for three independently controlled
hosts or VMs. Empirical histories are not a proof of every distributed execution.

## Advertised consistency

Quorum reads commit a fresh current-term barrier on the selected leader and read
only its committed/applied state. They fail explicitly when confirmation is
unavailable. Local reads expose a node's applied position and may be stale; they
are not advertised as linearizable current-head reads. Named writes carry an
exact retained request identity and canonical intent across leadership changes.

A successful applied response follows durable quorum acceptance and durable
local commit publication. A timeout after proposal is **uncertain**, not an abort.
Resolve it using the original request identity and intent; never issue a new ID
to guess whether the old attempt committed. Chosen conflicts are durable no-op
outcomes. Invalid/pre-admission failures and ambiguous failures are distinguished
in traces and in the reference model.

Invocation and response intervals come from actual API boundaries. Independent
clients on different machines cannot compare wall clocks without uncertainty;
the controller records causally safe coordinator intervals and preserves clock
observations separately. The checker searches permitted serial histories; sorting
replication log indexes is not a substitute for checking observations and
real-time precedence. Local follower reads are checked against valid applied
prefixes separately from quorum-read linearizability.

## Cluster history identity

A historical position names the partition identity and exact committed log
index/term. It is unrelated to a local Engine WAL sequence. The immutable genesis
configuration and application policy bind continuation tokens; an online
membership epoch does not change the meaning of retained positions.

Historical point, byte-range, typed JSON and whole-word queries reconstruct from
the verified retained replicated snapshot plus complete committed entries. They
never execute an uncommitted suffix. A follower that lacks the exact applied
position returns an availability error; the API does not silently substitute its
head or a different position. Beyond a node's known log is not proof that a
position is globally in the future. Foreign identity, expired history, known but
unapplied positions and term mismatch have distinct errors.

Results have byte-key ordering and bound their result rows, result bytes,
predicate complexity and replayed storage. Continuations bind query, identity,
position and last key. Maintenance may expire a cursor and does not pin its
retention horizon. An admitted read retains its immutable captured source or
exclusive replica observation for its execution. No cross-partition snapshot is
claimed. Historical plans honestly report bounded canonical replay/scan when
distributed historical indexes are unavailable.

## Controlled voter replacement

Exactly three established voters remain the supported configuration. Stage one
fresh learner, catch it up to the committed boundary, enter joint consensus, then
finalize the new three-voter set. Joint elections and commits require a majority
of **both** old and new voter sets, not a majority of their union.

Only one transition may be pending. Node IDs increase and cannot be recycled.
The leader must remain in the new set; hand over leadership before replacing it.
Restart derives membership from verified configuration history. An old directory
must not resurrect an obsolete configuration. Unsafe reductions, incomplete
predecessors and premature learner voting are rejected.

Transport endpoints are loaded at process startup. Pre-enroll one prospective
learner while the quorum is healthy. A later endpoint window requires planned
rolling restarts; the candidate has no hot endpoint reload or zero-downtime claim
for adding an unenrolled endpoint after a voter has already failed.

The two retained old voters and fresh learner must negotiate Atlas protocol 2
and the joint-consensus capability before administration. The retiring voter may
be unavailable; Atlas participants reject its legacy peer protocol. Membership records and
snapshots use explicitly newer envelopes. A legacy binary must refuse their
metadata rather than attempt a downgrade. Fixed-membership legacy operation and
new membership-enabled operation are separate compatibility modes.

## Cross-host operation and fault model

Atlas's private-network transport is explicit opt-in. It enrolls private IPv4
endpoints and optional bounded directed proxy routes. It provides framing,
integrity checks and version/capability checks, not network authentication or
encryption. Use independently secured private networking or SSH tunnels.

The host controller requires independent host/boot identities, pinned SSH host
keys, source/executable hashes, isolated owned storage and recorded runtime
configuration. LAN, WAN and asymmetric profiles record every delivered, dropped,
delayed, duplicated and reordered RPC. Process kills, stale-leader return,
follower ENOSPC and interrupted transfer are identified by observed events,
not configured intent. Resource-limit simulations are not actual disk-full tests.

Safety does not depend on making progress during a partition. Liveness is measured
only with eventual connectivity, a functioning durable majority, sufficient
bounded storage and available runtime workers. SIGKILL is not hardware power-loss
testing. Checksums do not authenticate coherent rewrites or whole-directory
rollback; the agreed Cerberus forgery limitation remains explicit.

## Upgrade and recovery contracts

Supported version pairs must be named and actually tested. Follower-first
replacement keeps a durable majority available; leader handover precedes its
replacement. Interrupted upgrades must restart without changing cluster identity.
Unsupported wire capabilities, snapshots, persistent metadata and downgrades fail
closed. New membership mode is never enabled merely because an old peer can parse
a legacy RPC.

Quorum-preserving recovery rebuilds a failed follower from verified replicated
state under the existing cluster identity. **Quorum-lost disaster restoration is
a different procedure:** verify a backup, initialize a new explicit partition
identity and fence the old deployment. A backup may omit previously acknowledged
operations after its captured prefix. That potential loss must be recorded, never
described as ordinary failover or zero-data-loss recovery.

## Fixed performance qualification

The immutable 1.0 baseline is
`54c92946abbaea30bae25e2e8178676e17cbd9e8`. The 0.8.2 comparison remains historical
context and cannot replace that baseline after measurement.

| Metric | Gate |
| --- | --- |
| Current-head p50 and p95 | Each at most 1.10 times the pinned 1.0 build |
| Cold historical p95 | At most 0.50 times the same baseline workload |
| Historical answers | Exact independent-reference parity |
| Long historical reads | Explicit bounded caches/admission and measured memory samples |
| Replication overhead | Actual latency/throughput versus single-node mode, consistency/durability stated |

Repeated paired runs retain every raw latency sample, executable hash, dataset,
history depth, cache state, hardware, concurrency and durability setting. Query
cache coldness is distinguished from uncontrolled OS page-cache coldness. In-process
durable replication measurements are labeled separately from network throughput.
Misses and bottlenecks remain public. Correctness failures stop release;
performance misses require a fix or an explicit scope revision, never a silently
weaker baseline.

## Scope and evidence

Milestones are 1.1 Foundation, 1.2 Fault Dominion, 1.3 Moving Quorums,
1.4 Continuous Operations and 1.5 Atlas Qualified. The four final deliverables are
the qualified engine, distributed fault harness, operator guide and public
qualification report. Raw histories, schedules, reference witnesses, source and
executable fingerprints and all benchmark samples must remain reproducible.

SQL, joins, automatic sharding/rebalancing, active-active regions, general
cross-partition transactions, unlimited retained history and production SLA
claims are out of scope. Arbitrary destruction of quorum storage cannot promise
zero data loss. Native artifacts, registry publication and website deployment
remain separate verified publication steps.
