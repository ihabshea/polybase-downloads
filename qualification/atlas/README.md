# Project Atlas — candidate evidence

Atlas is **not a qualified 1.5 release**. The user chose to continue locally and
keep the three-host gate open. The published database download is 1.0.0. See the [availability correction](AVAILABILITY_ERRATUM.md) for stale text inside immutable snapshots.

The [release contract](../../ATLAS_1_5.md), [operator guide](../../ATLAS_OPERATIONS.md),
[standalone fault harness](harness/README.md) and
[independent recorded-observation tools](tools/README.md) are available for review.
The public QA sources contain no Polybase engine or server implementation.

## Current measured candidate

[Source `b2c865f`](iterations/b2c865f/README.md) repeats the same 50,000 seeded
histories and 1,000-history overlay variant with zero recorded reference mismatches,
invalid traces or inconclusive passes. These are not 100,000 distinct histories.
All eight real rolling-restart SIGKILLs and named fixed-mode compatibility checks pass.

The final paired benchmark passes **11/12 current-head** and **36/36 cold-history**
targets. The remaining 1K range p95 is 34.927 µs versus 30.202 µs baseline (1.156×),
above the unchanged 1.10× target. Performance qualification remains **failed**.
The warm-history diagnostics retain 11/36 cases above 1.10× at p50 or p95.
All 84 cases, all three repeats, memory and throughput evidence are preserved.
The baseline is still `54c92946abbaea30bae25e2e8178676e17cbd9e8`.

## Preserved first iteration

[Source `333c2f0`](iterations/333c2f0/README.md) records:

- 50,000 local tmpfs-backed histories, 825,401 recorded client operations and no
  reference violation, invalid trace or inconclusive result counted as a pass.
- A separate 1,000-history overlay-backed campaign.
- Eight actual rolling-restart SIGKILLs, supported fixed-mode upgrade checks and
  old-version refusal with unchanged directory bytes.
- An independent public reference search and stored-payload audit of all 50,000
  histories, plus the separate 1,000. It does not authenticate engine execution
  or capture completeness.
- A valid, failed performance qualification: **5/12 current-head targets passed;
  36/36 cold-history p95 targets passed**. All 84 cases, three repeats, raw samples,
  memory and local synchronous replication measurements remain intact.

The 250,000 same-process Replica drop/reopen events in the large campaign are
not SIGKILLs. Scheduled message faults are not actual cross-host network faults.
Individual historical page cursors and dropped/delayed reorder offsets were not
stored; those two recorder counters are not independently reverified.

Raw gzip histories and independent witnesses are distributed separately from
Git in the [explicit local-evidence prerelease](https://github.com/ihabshea/polybase-downloads/releases/tag/atlas-local-evidence-2026-10-25-333c2f0).
The immutable [asset manifest](iterations/333c2f0/ASSET-MANIFEST.json) gives the
exact names, byte sizes and SHA256 identities. Its `staging_only`/`published:false`
fields describe packaging time; a later publication receipt records actual
availability. No native engine binary is in these evidence assets.

The first failures are not overwritten, excluded or converted into passing
measurements. Passing bounded observations does not prove every distributed
execution, hardware power-loss survival or authenticated storage.

[Verified publication receipt](publication/333c2f0/PUBLICATION.json) records all 27 remote digests and the anonymous download probe.

[Current b2 raw evidence](https://github.com/ihabshea/polybase-downloads/releases/tag/atlas-local-evidence-2026-10-25-b2c865f)
contains the 27 hash-verified raw-history/witness assets and manifests. Its
[publication receipt](publication/b2c865f/PUBLICATION.json) records remote digests,
the anonymous download/gzip probe and the preserved latest-stable 1.0.0 identity.
[Implementation-input equivalence](integration/upstream-main-equivalence.json)
and [executed integration guards](integration/validation.json) document the later
presentation/publication merge. The [hosted CI observation](integration/hosted-ci-observation.json)
remains failed before executed steps; local checks are separately documented.

## Website candidate

The [isolated production website proof](website-production/README.md) preserves
unchanged 1.0 native guards and download targets. Actual browser QA passed 224
responsive checks, 104 accessibility scans and seven behavior scenarios; the
final wording-only delta is recorded and rechecked separately. The
[preview QA](website-preview/report.json) remains labeled separately.
A static website artifact is a publication input, not a live deployment.
No Sites deployment capability is available in this session.

[Download the verified static website candidate](https://github.com/ihabshea/polybase-downloads/releases/download/atlas-local-evidence-2026-10-25-b2c865f/polybase-atlas-website-candidate-static.tar.gz).
Its separate [website publication receipt](publication/website-b2c865f/PUBLICATION.json)
records archive verification and the unchanged original raw-evidence assets.
The canonical site was not redeployed.
