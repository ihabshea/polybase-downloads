This is **evidence only**, not a downloadable Polybase 1.5 engine or a qualified Atlas release. The existing stable database download is [Polybase 1.0.0](https://github.com/ihabshea/polybase-downloads/releases/tag/v1.0.0).

Measured source: `b2c865f0c8299e7f54784d81d012d35aa7b79512`.

- Local recorded histories: 50,000, three real Replica directories in one process, scheduled transport, tmpfs storage. This repeats the same seeds as the preserved 333c2f0 campaign; the two runs are not 100,000 independent histories.
- Separate overlay-backed local campaign: 1,000 histories.
- Independent checking validates supplied recorded observations and witnesses. It does not execute the engine, authenticate capture or establish real network/process execution.
- Separate same-host rolling wire campaign: 8 observed SIGKILL exits. Same-process drop/reopen observations are not SIGKILL deaths.
- Fixed paired benchmark against immutable 1.0 source 54c92946: 11/12 current-head targets and 36/36 cold-history p95 targets passed. Remaining miss: 1K range p95, 34.927µs versus 30.202µs (1.156×). All misses and the first 333c2f0 results remain preserved.
- Cross-host histories/fault schedules: 0. The three-independent-host gate and full 1.5 release gate remain open.

The 25 raw-history/witness payloads and two manifest/checksum files are synthetic qualification data. There are no native engine executables in this release. Each GitHub-computed SHA-256 and byte size is checked against its local source before publication.

[Source-qualified reports, benchmark samples and limitations](https://github.com/ihabshea/polybase-downloads/tree/feature/1.5-atlas/qualification/atlas/iterations/b2c865f). [Preserved first 333c2f0 evidence](https://github.com/ihabshea/polybase-downloads/releases/tag/atlas-local-evidence-2026-10-25-333c2f0).

SIGKILL is process-crash testing, not hardware power-loss qualification. Checksums provide integrity comparison, not authenticated capture or protection against coherent rewrites.
