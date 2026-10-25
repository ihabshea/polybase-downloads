# Project Atlas — candidate evidence

Atlas is **not a qualified 1.5 release**. The user chose to continue locally and
keep the three-host gate open. Published database downloads remain 0.9.0.

The [release contract](../../ATLAS_1_5.md), [operator guide](../../ATLAS_OPERATIONS.md),
[standalone fault harness](harness/README.md) and
[independent recorded-observation tools](tools/README.md) are available for review.
The public QA sources contain no Polybase engine or server implementation.

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

Follow-up code is being requalified against the same immutable 1.0 baseline,
`54c92946abbaea30bae25e2e8178676e17cbd9e8`. The first failures are not overwritten,
excluded or converted into passing measurements. Passing bounded observations
does not prove every distributed execution, hardware power-loss survival or
authenticated storage.

[Verified publication receipt](publication/333c2f0/PUBLICATION.json) records all 27 remote digests and the anonymous download probe.
