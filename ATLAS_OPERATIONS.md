# Atlas operator guide

**Polybase 1.5.0-preview.1 candidate.** This guide describes implemented candidate
commands and their operating contract. It does not declare Atlas qualified or
downloadable. The public database download is 1.0.0. The real three-host
qualification gates remain open; local processes, simulated transport and tmpfs
reopen tests cannot close them. See the [release contract](ATLAS_1_5.md),
[tracker](ATLAS_1_5_TRACKER.md) and [cross-host procedure](ATLAS_CROSS_HOST.md).

## Establish one partition

Atlas supports one replicated partition with three established voters and one
learner during a single replacement. It does not provide cross-partition
transactions or global snapshots across databases. Each node owns a separate
directory on a supported local POSIX filesystem. Never share one backing directory
between nodes, remove a live ownership lock, or edit consensus metadata to make a
node join.

Build from an authorized private checkout with the recorded Rust toolchain
(minimum Rust 1.89); Python 3.11 or newer runs the examples and tooling:

```sh
cargo build --release --locked -p polybase-cli --bin polybase-node
```

Record the source SHA, executable SHA256, toolchain and configuration before
deployment. Use the same reviewed executable on the Atlas participants. The
examples below use illustrative private addresses; they are not measured or
qualified infrastructure.

Create `atlas.json` with a fresh, nonzero 16-byte partition identity encoded as
32 hexadecimal characters. Keep `genesis` unchanged across replacement and
restart. Enroll the future learner endpoint before replacement:

```json
{
  "partition": "b642398fe7a54123a9c165b3dd763a10",
  "genesis": [1, 2, 3],
  "transport": "trusted_private",
  "nodes": [
    {"id": 1, "address": "10.44.0.11:7341"},
    {"id": 2, "address": "10.44.0.12:7341"},
    {"id": 3, "address": "10.44.0.13:7341"},
    {"id": 4, "address": "10.44.0.14:7341"}
  ],
  "routes": []
}
```

The config accepts three or four distinct enrolled private IPv4 endpoints. An
optional directed route has the form
`{"from":1,"to":2,"address":"127.0.0.1:17412"}` and overrides only traffic
from node 1 to node 2. Its proxy or tunnel must already exist on the sending
host; the reverse route is independent. There are at most 12 directed routes.

Endpoint enrollment is loaded when each process starts; it is not hot-reloaded.
Pre-enroll the prospective learner while the current quorum is healthy. A later
four-endpoint window requires a planned rolling configuration restart. Adding an
unenrolled replacement after a voter has already failed can temporarily remove
quorum availability while survivors restart; that path has no zero-downtime claim.

The transport provides **no authentication or TLS**. Use an independently secured
private network or trusted SSH tunnels and protect the client/admin port. CRC
framing detects accidental damage; it does not authenticate a peer, an operator
or coherently rewritten storage. Do not expose this interface to untrusted
clients or the public Internet.

On each respective host, create an empty owned directory and start that node:

```sh
mkdir /srv/polybase/node-1
target/release/polybase-node atlas.json 1 /srv/polybase/node-1 --atlas-network
```

Repeat with IDs 2 and 3 and their own directories. ID 4 can start in an empty
directory as a nonvoting learner; starting it does not make it a voter. Existing
replica directories must retain their original identity/binding. Start commands
do not reset them. `--lab-controls` is for isolated fault experiments and is not
needed for normal administration.

## Read the advertised consistency

From the repository root, the existing Python helper sends the actual framed
client protocol. Its `rpc` function returns successful values and raises
`RuntimeError` containing the wire error code on an error response. A production
client should preserve the structured error code and leader hint.

```python
import sys
sys.path.insert(0, "qualification/atlas/harness")
from cluster_driver import rpc

addresses = {1: "10.44.0.11:7341", 2: "10.44.0.12:7341",
             3: "10.44.0.13:7341", 4: "10.44.0.14:7341"}
print(rpc(addresses[1], {"op": "hello"}))
print(rpc(addresses[1], {"op": "status"}))
```

Atlas `hello` reports protocol 2, `trusted_private`, partition, immutable genesis,
node identity and capabilities including `atlas-joint-v1`. A local `role=leader`
status is a hint, not evidence of a functioning majority. Select a node and
require a successful fresh quorum snapshot before treating it as the available
leader:

```python
all_rows = {"key_prefix": "", "predicate": "any", "value": ""}
snapshot = rpc(addresses[1], {"op": "snapshot", "query": all_rows,
                            "mode": "quorum", "minimum": None})
print(snapshot["position"], snapshot["term"], snapshot["rows"])
```

`quorum` commits a fresh current-term barrier and reads committed/applied state.
It fails if the selected node cannot confirm that barrier; the runtime does not
silently route the request or downgrade it to a local read. `local` reads the
selected node's applied prefix and may be stale. Both return the actual position
and term. An empty row set at an admitted position is a valid answer.

To require at least a known prefix on a follower, use the legacy current-read
`minimum` shape with integer fields:

```python
minimum = {"index": int(snapshot["position"]), "term": int(snapshot["term"])}
local = rpc(addresses[2], {"op": "snapshot", "query": all_rows,
                         "mode": "local", "minimum": minimum})
```

This can return a newer applied prefix; it is not an exact historical read.
`behind` means this node cannot satisfy the minimum. Check the named term too;
an index alone is not an identity. Do not pass large consensus integers through
JavaScript floating-point numbers. Historical targets below use decimal strings.

## Write once and resolve uncertainty

Issue a token on the confirmed leader, save its canonical spelling and exact
intent before submission, and keep both across retries and leader changes.
Keys and values on this wire are hexadecimal bytes:

```python
leader = addresses[1]  # Already confirmed with a successful quorum read.
token = rpc(leader, {"op": "issue"})["request_token"]
intent = {
    "reads": [{"key": "616c706861", "value": None},
              {"key": "62657461", "value": None}],
    "mutations": [{"key": "616c706861", "value": "6f6e65"},
                  {"key": "62657461", "value": "74776f"}]
}
receipt = rpc(leader, {"op": "write", "token": token, "intent": intent})
print(receipt)
```

Every mutation in this wire API requires an expected value for its key. There
are at most 64 expected keys and 64 mutations; expected keys must be unique.
`None` means expected absence or, in a mutation, deletion. Expectations compare
bytes, so an ABA cycle back to the same value can satisfy them. The batch either
applies atomically or has a chosen no-mutation outcome.

`status=applied` with `durable=true` acknowledges the chosen atomic batch.
`status=conflict` is a retained, durable no-mutation decision. A later identical
retry returns the original position/status, even if the expected condition has
since become true. `replayed=true` identifies a duplicate write application.
Barriers, rejected requests and duplicate attempts can consume consensus log
entries; application event positions need not be contiguous.

A transport timeout, lost connection, `uncertain` response or fenced process does
not prove the write aborted. After finding a leader with a fresh quorum read,
look up the **original** token and intent:

```python
outcome = rpc(leader, {"op": "outcome", "token": token, "intent": intent})
```

If it is `absent`, the lookup proved absence at its confirmed observation; it
did not cancel an outstanding proposal. Retry that same token and exact intent
to obtain a terminal retained result. Never substitute a new token to resolve a
timeout. Changing intent under the same retained token returns
`request_mismatch`. Explicit request-history expiry can make an old token
`request_expired`; keep deduplication requirements within the retained horizon.

| Observed outcome | Operator/client action |
| --- | --- |
| `not_leader` | Treat the leader hint as a hint; confirm a leader, then retry the same intent/identity |
| `quorum_unavailable` | No confirmed current read; restore eventual majority connectivity/resources |
| `uncertain` or missing write reply | Resolve the original token; do not infer abort |
| `conflict` receipt | Chosen no-op; a new business attempt needs a deliberate new identity |
| `capacity` | Respect bounded admission/storage; inspect the failed operation and maintain safely |
| `request_mismatch` / `request_expired` | Stop automatic rewriting/reissuing; resolve the application's retained intent policy |
| `corruption` / `storage_error` | Preserve files/logs and stop using the failed instance; do not clear metadata to force startup |

## Read an exact historical commit

A cluster historical target is `(partition, committed log index, term)`. It is
not the backing Engine's WAL sequence. The partition identifies the cluster
generation; online membership replacement does not change retained answers.
Use the receipt or a returned snapshot as the source of an exact target:

```python
target = {"partition": "b642398fe7a54123a9c165b3dd763a10",
          "index": receipt["position"], "term": receipt["term"]}
point = rpc(addresses[2], {"op": "historical", "request": {
    "kind": "get", "target": target, "key": "616c706861"}})
```

`index` and `term` must be canonical decimal strings: no leading zeros except
`"0"`, signs, fractions or overflow. A historical `value=None` is valid absence
at that exact admitted commit. It is different from an unavailable position.
No follower forwarding or automatic catch-up is performed by this call.

The query form supports byte ranges, typed JSON, scalar and whole-word search:

```python
request = {
    "kind": "query", "target": target,
    "range": {"start": {"key": "61", "inclusive": True},
              "end": {"key": "63", "inclusive": False}},
    "predicate": {"kind": "any"}, "cursor": None, "page_size": 32
}
page = rpc(addresses[2], {"op": "historical", "request": request})
# Preserve all other request fields for the next page.
if page["next"] is not None:
    request["cursor"] = page["next"]
    next_page = rpc(addresses[2], {"op": "historical", "request": request})

# Separate queries for JSON/document values:
for predicate in [
    {"kind": "json", "predicate": {"op": "eq", "path": ["n"], "value": 1.0}},
    {"kind": "text", "text": "amber history"},
    {"kind": "scalar", "path": ["n"], "value": 1}
]:
    request["cursor"] = None
    request["predicate"] = predicate
    print(rpc(addresses[2], {"op": "historical", "request": request}))
```

Use `start=None` or `end=None` for an unbounded range. Pages contain
at most 64 rows in byte-key order. Typed JSON equality preserves numeric
equivalence such as `1` and `1.0`; legacy scalar search keeps its documented
representation-sensitive semantics. Text requires all supplied whole words.
`explain` identifies the exact position and actual bounded reconstruction/scan
work; historical indexes are not promised.

| Historical wire code | Meaning |
| --- | --- |
| `foreign_partition` | Wrong cluster generation/identity |
| `history_expired` | Requested prefix is below this node's retained floor |
| `history_not_applied` | Locally known index has not committed/applied here |
| `history_unavailable` | Beyond this node's known log; not proof of a globally future index |
| `history_term_mismatch` | Locally known index belongs to another term |
| `invalid_position` | Invalid zero/nonzero index/term pair |
| `invalid_request` | Malformed wire values, including noncanonical decimal target strings |
| `invalid_cursor` | Damaged cursor or different query/target/context |

`compact` can advance the node's retained floor and expire later continuation
calls. A cursor does not pin history. Inspect retention requirements before
maintenance; do not substitute the current head when an old page expires.

## Replace one failed voter online

Keep a durable majority available. The retiring voter may remain offline. The
two retained old voters and the fresh learner must negotiate Atlas protocol 2
and matching joint-consensus capability. A protocol-1 peer is not eligible merely
because it parses the old frame. Node IDs must be fresh and strictly greater
than the highest introduced ID; never reuse a retired directory or ID.

After starting enrolled node 4 in its new empty directory, replace failed voter
3 through the confirmed leader, which must remain in the new set:

```python
print(rpc(leader, {"op": "prepare_replacement", "remove": 3, "add": 4}))
# Wait for actual catch-up; premature entry returns an explicit rejection.
print(rpc(leader, {"op": "enter_joint"}))
print(rpc(leader, {"op": "finalize_replacement"}))
print(rpc(leader, {"op": "status"})["committed_membership"])
```

Preparation stages a nonvoting learner under the old three-voter quorum. Joint
elections and commits require a majority of both old and new sets. Finalization
uses the new three-voter set. Only one transition may be pending, and each
predecessor must commit before the next phase. After an uncertain admin reply,
inspect actual `membership` and `committed_membership` before choosing the next
action; repeated blind phase commands are not a rollback procedure.

To replace the leader, first request handover to another caught-up established
voter while no replacement is pending:

```python
print(rpc(leader, {"op": "handover", "target": 2}))
confirmed = rpc(addresses[2], {"op": "snapshot", "query": all_rows,
                             "mode": "quorum", "minimum": None})
leader = addresses[2]  # Only after that actual quorum request succeeds.
```

Handover is a request to campaign, not an instantaneous leadership guarantee.
Do not stop the old leader because the handover request alone returned success.
After finalization, fence the retired service and preserve its old directory for
investigation or archival. A stale return must not rejoin as a new identity.
Never roll back membership by copying old metadata or starting a legacy mode on
an Atlas membership directory.

## Upgrade and recover deliberately

The candidate rolling-compatibility path is **1.0.0 to 1.5.0-preview.1 in the
fixed-membership loopback protocol-1 mode**. Its recorded qualification status
is separate from this guide; do not infer that every intermediate or older
version pair is supported. Its bounded compatibility fixture upgrades one
follower, verifies catch-up and quorum availability, then upgrades the next
follower before the former leader. Never stop two established voters together.
The fixture's fixed-mode handover uses an explicitly pre-enabled lab campaign;
the Atlas `handover` command above is protocol-2 administration and is not an
API of the 1.0 binary. This fixture is not a general production fixed-mode
handover procedure. Confirm its actual report and limitations before choosing
an operational upgrade path.

Enable Atlas protocol 2 only with compatible participants and explicit Atlas
configuration. Legacy protocol 1 and Atlas protocol 2 are separate modes, not a
mixed membership protocol. Accepted membership writes newer metadata/snapshot
envelopes; old decoders must refuse them. New binaries also refuse legacy-mode
startup on an Atlas membership directory. Unsupported downgrade is not a
recovery tool. If an upgrade is interrupted, restart the compatible binary on
the same verified identity/directory and inspect actual state before proceeding.

With a functioning majority, normal follower recovery retains the existing
cluster identity and obtains verified state through replication/snapshot
catch-up. Restart an intact follower directory, or perform the documented fresh
ID replacement when that voter cannot be recovered. Do not clone a live
directory, truncate a WAL or force a locally stale prefix to become authoritative.

### Capture an offline backup

Stop one follower at a time while preserving the other voters' majority. The
backup command opens that stopped directory exclusively, captures and verifies
its replica state, and writes a new backup file:

```sh
target/release/polybase-node backup atlas.json 2 /srv/polybase/node-2 /backups/atlas-node-2-new --atlas-network
```

Save the command's JSON provenance and the backup file's SHA256 alongside its
captured applied index/term, then restart
the follower and verify catch-up before stopping another voter. A stopped
follower's backup is **not a newly quorum-confirmed current-head snapshot**.
Any writes after its applied boundary may be absent. Backup verification does
not promote that boundary or qualify arbitrary hand-edited files.

### Restore after quorum loss

Quorum-lost restore is an explicit disaster operation with possible loss of
previously acknowledged writes. Fence all old services/endpoints first. Verify
the selected backup and record the chosen applied boundary and potential loss.
Create a new Atlas config with a **different fresh partition identity** and
exactly three enrolled genesis voters. Choose an entirely new output root; do not reuse the source
directory or an old deployment's root:

```sh
target/release/polybase-node restore atlas.json 2 /backups/atlas-node-2-new restored-atlas.json /srv/polybase/restored-new --acknowledge-quorum-lost --source-atlas
```

The command creates `NEW_ROOT/ATLAS_RESTORE_INCOMPLETE.json` and synchronizes it
before bootstrapping the three `NEW_ROOT/<node-id>` directories. After verifying
all three offline, it writes and synchronizes `RESTORE_MANIFEST.json`, then
removes the incomplete marker. A failure leaves quarantined evidence intact;
startup refuses a node beneath an incomplete root. Do not remove the marker or
move a partial directory to bypass that check. This is protection for cooperating
operators, not authentication.

The completed manifest reports `network_started:false` and
`potential_acknowledged_data_loss:true`. The new prefix starts at index/term
`1/1`. It retains the selected application bytes under the new identity; old
named retry receipts are not transplanted. Old tokens and old
historical positions belong to the old partition and are foreign to the new
cluster. Preserve the manifest and source backup. Start the three restored
nodes using the new config, then require an actual quorum read and validate the
selected application state before admitting traffic. Never reconnect the old
deployment to the restored service or describe this procedure as zero-loss
failover. `--source-atlas` identifies an Atlas source config; omit it only for a
verified fixed-membership source config.

## Preserve qualification evidence

Use the [cross-host procedure](ATLAS_CROSS_HOST.md) for independently controlled
hosts/VMs, not the convenience three-process fixture in `cluster_driver.py`.
Retain raw controller invocation/response intervals, host identity observations,
network/process schedules, source and executable fingerprints, configs and
checker witnesses. Remote monotonic clocks cannot be compared as one global
clock. An invalid or exhausted bounded checker is a failing/inconclusive gate,
never a passing history. A seed reproduces a recorded program; it does not force
the operating system's physical schedule.

Performance gates use the pinned clean 1.0 commit
`54c92946abbaea30bae25e2e8178676e17cbd9e8`, paired source-bound executables and
all raw samples. Record dataset/history depth, cache state, hardware,
durability, consistency mode and concurrency before interpreting ratios.
See [the performance protocol](ATLAS_PERFORMANCE.md). Publish misses rather
than changing the baseline, filtering slow samples or substituting estimates.
SIGKILL/restart evidence is not a hardware power-loss test. Local empirical
success is not formal proof or completion of the open real cross-host gates.

The public standalone fault controller and RPC helper are in [qualification/atlas/harness](qualification/atlas/harness/README.md). Full engine builds require the private source; the public QA tools do not contain the engine.
