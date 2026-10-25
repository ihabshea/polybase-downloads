# Atlas iteration 01 — immutable 333c2f0 counterexample

This directory preserves the first complete measured Atlas iteration at source
`333c2f0ecf25c5987087f7cecc0bcd9fe269af73`. Later optimization work must retain
these results as a separate iteration. No original result, sample, configuration,
log or source check was rewritten or relabeled during packaging.

The first paired performance campaign is a **failed qualification**: 7 of 12
current-head target cases missed (5 passed), while all 36 cold-history target
cases passed. Measurements were valid and correctness parity passed. The entire
29-file performance directory is retained byte for byte, including raw samples,
all 84 pooled cases, 252 repeat cases, 5,004 measured sample pairs, detailed
results, TSV, runtime configuration and before/after source checks. The pinned
1.0 baseline and first candidate executable hashes remain unchanged in the
original reports. Executables are preserved privately, not distributed here.

The separately recorded local campaigns comprise 50,000 fresh-cluster histories
using actual Replica APIs with tmpfs storage and 1,000 additional overlay-backed
histories. Transport and client scheduling are in one process. `restarts` mean
Replica drop/reopen within that process, not SIGKILL. Neither campaign establishes
cross-host behavior or hardware power-loss survival. Their reports, all eight
shard summaries/configurations/logs and independent recorded-observation audit
reports are preserved here; compressed raw histories and successful witnesses
are external evidence assets described by `ASSET-MANIFEST.json`.

The rolling compatibility evidence is separate: it contains actual same-host
processes and eight observed SIGKILL exits. All raw RPC observations, reports,
configurations and logs are preserved publicly. This is fixed-genesis rolling
wire compatibility, not cross-host deployment, SDK parity or an independent
linearizability search. Small opaque on-disk Replica/WAL fixtures are preserved
only in the private iteration copy and listed explicitly in the preservation
manifest. No engine/server implementation or native executable is included.

The independent public audit checks supplied recorded observations. It does not
authenticate execution, capture completeness or claimed source labels. Local
reads are checked for declared-prefix consistency; only quorum-labeled reads
receive interval linearizability checks. Individual page boundaries/cursors and
reorder offsets for dropped/delayed messages are absent from the raw payloads:
`historical_pages` and `message_reorders` remain recorder-only counters. The
canceled serial verification prefix is explicitly nonqualifying and excluded;
all eight complete shard audits are required for the 50,000-history aggregate.

`PRESERVATION-MANIFEST.json` records every original path, byte size and SHA-256,
its public/private destination, and each omitted gzip's evidence-asset mapping.
Original small artifacts were copied directly, without JSON reserialization.
`PACKAGING-AUDIT.json` records byte comparisons, hardlink checks, native-binary
exclusion and the preserved failed performance gate. `SHA256SUMS.json` covers
this Git directory. The separate MIT public QA tools remain unchanged outside
this iteration. At packaging time, assets are staged only; this operation did
not commit, push, create a GitHub release or publish a downloadable database.
