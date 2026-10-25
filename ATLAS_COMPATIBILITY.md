# Atlas compatibility, upgrades and recovery

This is the compatibility contract for the 1.5.0-preview.1 engineering candidate.
The [Atlas release gates](ATLAS_1_5.md) still require separate distributed,
correctness and performance evidence. A successful rolling run is evidence for
the exact executable pair and bounded workload recorded in its report.

## Explicit version pairs and modes

| Pair / mode | Contract |
| --- | --- |
| 1.0.0 at `54c92946abbaea30bae25e2e8178676e17cbd9e8` and 1.5.0-preview.1, legacy fixed genesis | Supported rolling path tested by `run-atlas-upgrade.py`; exactly voters 1, 2, 3 and unchanged legacy configuration |
| 1.5.0-preview.1 with Atlas protocol 2 on all retained voters and the learner | Membership-capable mode; tested separately from mixed-version rolling operation |
| 1.0.0 with Atlas membership records or snapshots | Unsupported; old binary must reject the newer durable envelope |
| 1.5.0-preview.1 started in legacy mode on non-genesis membership | Refused at startup; restart using the explicit Atlas network configuration |
| Other old versions, arbitrary version pairs or arbitrary voter counts | No compatibility claim |

The pinned 1.0.0 node executable used by the rolling runner has SHA-256
`46cd7200219ab308fe725406cb5f24d883722afe43923819fea60d6989dd3d68`.
The runner refuses another baseline digest or version banner. It records the
actual candidate digest and banner before and after execution. Rebuilding an
old source tree with different tooling can produce a different digest; that is
a different executable pair requiring an explicitly reviewed qualification.

## Persistent and transport boundaries

The immutable replica ownership marker binds the partition, node, **genesis**
three-voter set and application policy. `Config.members` continues to mean that
genesis set after replacement. Never edit it to the current voters, rewrite the
marker or copy a stale voting directory into a live partition. The accepted and
committed `Membership` observations expose the current configuration separately.

| Envelope | Fixed genesis | Membership-capable state |
| --- | --- | --- |
| Local Engine WAL/frontier and entry envelope | Existing format unchanged | Existing format unchanged |
| Replica ownership marker | `PBREPL01` | Same immutable genesis binding |
| Durable replica metadata | `PBHARD01` | `PBHARD02` with the accepted membership state |
| State-machine snapshot | `PBFSM001` | `PBFSM002` with the committed membership state |
| Membership command | Absent | Checksummed `PBMEM001` Prepare / Joint / Finalize |
| RPC frame | Checksummed `PBRPC001` | Same bounded frame, explicitly different peer packet |
| Peer packet | `kind: peer` | `kind: atlas_peer`, `protocol: 2` |

New readers retain the old envelopes. Old readers reject the newer metadata and
snapshot headers. The newer metadata is selected when a non-genesis membership
transition is accepted; snapshots use the newer format once that membership is
committed. A legitimate overwrite of an **uncommitted** Prepare may return to
genesis metadata. This is not an irreversible feature fuse. Retained committed
replacement history cannot be downgraded or reinterpreted as genesis.

Atlas transport refuses legacy peer packets, and legacy mode refuses Atlas peer
packets and membership commands/snapshots. Legacy snapshot transport requires at
least eight bytes in its first chunk, preventing a fragmented first chunk from
hiding the snapshot version. The supplied legacy runtime uses 64-KiB chunks;
custom smaller-chunk transports are outside this mixed-version runtime contract.

Atlas administration checks `hello` responses for protocol 2, matching partition,
genesis and application policy, and the `atlas-joint-v1` capability. Both retained
old voters and the fresh learner must pass. The failed retiring voter can remain
offline; it cannot form an old quorum alone when retained Atlas voters fence its
legacy traffic. A version string or successful legacy RPC is not capability
negotiation. Private-network framing and capability checks are not authentication;
operators must secure the enrolled network independently.

## Follower-first rolling procedure

Keep the fixed-genesis configuration and storage directories unchanged while
replacing binaries. Keep enough available voters for quorum throughout.

1. Verify the exact old and new source/executable identities and preserve a
   verified backup. Inspect the current leader and committed/applied positions.
2. Stop one follower, replace its binary, reopen the same directory and confirm
   it catches up. Restart it again during the partial upgrade if qualifying the
   interrupted-upgrade path. Upgrade the other follower only after verification.
3. Ask an up-to-date new follower to campaign. A campaign response acknowledges
   the request only. Confirm it becomes leader and completes a fresh quorum read
   before stopping or replacing the former leader.
4. Resolve any uncertain named write with its **original** request identity and
   exact intent on the new leader. Require its original chosen position/outcome;
   never generate a replacement ID to guess the outcome.
5. Upgrade the former leader as a follower, verify all application rows and named
   outcomes, and retain all observed results and process/configuration identities.

The runner exercises a follower downgrade and re-upgrade **before any membership
transition**, using the unchanged fixed-format store. This does not permit an
old binary to open a post-replacement store. Enabling Atlas protocol 2 is an
explicit separate operational step; mixed protocol-1/protocol-2 availability is
not asserted by the rolling test.

## Online replacement

Enroll at most four active endpoints: three old voters plus one fresh learner.
Use a new node identity greater than all previously used identities. Stage one
follower replacement; hand leadership to a retained voter first if the node to
retire is currently leader. Prepare is ordered by the old quorum. Enter Joint
only after the learner has matched through the captured committed head. Joint
elections and commits require separate old and new majorities. Finalize only
after the joint entry is committed; the resulting voter set has exactly three
members. A later replacement can use a fresh identity and another four-endpoint
window. Arbitrary scaling and simultaneous replacements are rejected.

Every predecessor configuration must be committed before advancing its phase.
The latest **accepted** configuration already governs quorum decisions; waiting
until commit to enforce joint voting would be unsafe. Committed snapshots and
accepted log entries carry configuration history through reopen and catch-up.
Retired IDs cannot be reused. A stale retiree may continue attempting elections
from its old directory, but cannot resurrect its old quorum against current
members. Do not describe an isolated retiree's self-reported role as authority.

An administration timeout can leave a transition chosen or pending. Inspect the
accepted and committed epoch, phase and `changed_at` position before continuing.
Do not edit configuration files to force a result or assume a timeout aborted
the transition. The API does not provide an automatic rollback of a chosen
configuration.

## Quorum-preserving recovery and disaster restore

A failed follower can rejoin the same identity from its intact state and receive
verified log/snapshot catch-up while a healthy quorum continues. A new voter
identity must enter through learner/joint replacement. Copying an arbitrary
stale voting directory is not follower recovery.

For quorum-lost restoration, stop and fence the old deployment, verify the backup
and select a **new partition identity**. The offline backup records one replica's
committed prefix and provenance; it does not independently establish that this
is the freshest quorum prefix. Acknowledged operations after the backup may be
lost. The restore CLI requires explicit acknowledgement of that possibility and
initializes three empty, quarantined destinations. All three canonical states
must verify before its incomplete-restore marker is removed. A partial failure
remains quarantined. The tool starts no network service.

Restored application state begins at new position `(index=1, term=1)` with genesis
membership. Old request tokens, outcomes, subscriptions and historical positions
do not become positions in the new identity. Reconcile uncertain application
operations deliberately. Checksums detect covered damage; they do not authenticate
a coherent CRC-preserving forgery or malicious whole-directory rollback.

## Reproduce the rolling test

Build and pin the candidate before running against a fresh output outside the
source tree. The clean runner refuses dirty source and changed source/executable
fingerprints. It also records and compares configuration hashes before and after.

```sh
python3 -B scripts/run-atlas-upgrade.py \
  --out /tmp/polybase-atlas-upgrade-qualification \
  --old-binary /path/to/pinned-1.0.0/polybase-node \
  --new-binary target/release/polybase-node
```

Use `--development-allow-dirty` only for explicitly labelled development runs;
those runs cannot qualify frozen source. No existing output directory is reset.
The runner saves the raw request/reply JSON, frame digests and actual monotonic
client intervals in `observations.jsonl`, along with lifecycle events, binary
identities, configurations, process logs and the old-version refusal file-tree
comparison. Local snapshots must equal complete independently known byte-pair
states, and quorum reads must equal the latest acknowledged state. Retried named
operations must retain their original positions.

The lost-acknowledgement scenario deliberately reads and records a complete wire
ACK, then discards it before application delivery. The application retains an
uncertain operation until its cross-leader retry. This is an instrumented delivery
loss, **not** a claimed network fault or an unobserved timeout. The raw receipt
belongs to the independent test oracle. The runner also stages epoch-1 metadata
with the retiring voter absent, then invokes the actual pinned old binary and
requires explicit refusal plus identical file paths, lengths and byte hashes.

These are same-host process/wire tests. They neither execute an SDK nor search
for a linearizability witness, simulate hardware power loss, or satisfy the
50,000-history or 10,000-cross-host-schedule gates. Those remain separate recorded
campaigns. Preserve failures and publish the limits with any successful report.
