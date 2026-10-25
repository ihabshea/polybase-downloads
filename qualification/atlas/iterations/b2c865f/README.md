# Atlas iteration 02 — fixed measured source b2c865f

This directory preserves measurements and recorded observations for frozen source
`b2c865f0c8299e7f54784d81d012d35aa7b79512`. It does not claim that the repository's
later presentation/merge HEAD is this source. The first `333c2f0` iteration remains
separate, immutable and visible as the earlier performance counterexample.

The second paired campaign is valid, has exact correctness parity, and is still
a **failed performance qualification**: 11 of 12 current-head target cases pass.
The remaining 1,000-record narrow-range case has pooled p95 ratio
`1.156446592940865`, above the unchanged `1.10` target. All 36 cold-history target
cases pass, with p95 ratios `0.03555928935923049` through `0.24675677654089564`.
Eleven of 36 warm-history diagnostic cases exceed `1.10` at p50 or p95; those
results are retained rather than hidden. The whole 29-file performance directory
is copied byte for byte: all 84 pooled cases, 252 repeat cases, 5,004 sample pairs,
raw samples, complete results, TSV, runtime/source checks and before/after hashes.
No TSV line endings, JSON bytes, outliers, dataset, baseline or target was changed.

The main 50,000 fresh-cluster histories use actual Replica APIs with tmpfs storage
and tmpfs artifact output. The additional 1,000 histories use overlay-backed
Replica storage and are separate. Transport/client scheduling is in one process;
`restarts` are Replica drop/reopen, not SIGKILL or new OS processes. Neither corpus
qualifies cross-host deployment, disk-failure or hardware power-loss survival.
The independent recorded-observation audits check all eight full main shards,
global IDs/seeds/order, hash-linked witnesses, declared profile totals, source/
version labels and stable compressed inputs. Their false execution-authentication,
capture-completeness, cross-host and release flags remain explicit. Individual
page cursors and dropped/delayed reorder offsets are absent, so
`historical_pages` and `message_reorders` remain recorder-only counters.

The initial attempt to put 50,000 main artifacts on overlay was refused by the
unchanged conservative disk-reserve preflight before any build or engine case.
Both original refusal receipts are preserved under `preflight-refusal/`. The
successful main artifact output then moved to ample tmpfs space; the reserve was
not weakened and the refused attempt is not counted as a workload result.

The rolling corpus is separate same-host real-process fixed-genesis wire
compatibility evidence, including eight observed SIGKILL exits. Raw RPCs,
configurations, logs and reports are public. Opaque database fixtures are private
only and explicitly listed in the preservation manifest. This is not a cross-host
or SDK qualification, and no engine/server implementation or native executable
is included. Benchmark executables are preserved privately under guarded hashes.
The runtime/summary bind candidate hash `72d13e29...` and baseline `4c681dc2...`;
the reused candidate-build provenance file still labels the first333 build and
is intentionally not relabeled or presented as this iteration's identity.

Engineering logs from `/tmp/atlas2-*` are retained exactly. The existing MIT QA
tools are unchanged. Large raw histories and successful witness streams are
external assets, not Git payloads. `/tmp` main originals are hardlinked; the small
cross-filesystem overlay/witness files were copied with exact before/after hash
guards. `ASSET-MANIFEST.json` states each staging method and original path.
`PRESERVATION-MANIFEST.json` inventories every copied original and external-asset
mapping; `PACKAGING-AUDIT.json` and `SHA256SUMS.json` verify this package. Publication
is a separate operation; this packaging did not stage, commit, merge, push or
create a native release. Source-equivalence and publication receipts outside
iteration directories are maintained separately by the release coordinator.
