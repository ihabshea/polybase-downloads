# Independent successful-witness validation

`verify-linearizability-traces.py` is a standard-library-only reference checker
for the **supplied successful serial witness** in each Cerberus trace record.
It invokes neither the Rust checker nor the engine, does not search for a witness,
and does not claim that an invalid supplied witness means no valid witness exists.

The validator independently checks:

- Exact operation-ID coverage, without sorting operations by ID or receipt.
- Every real-time predecessor implied by invocation/response intervals.
- Byte-key point/range observations, read-your-writes and expected-value conditions.
- Atomic mutation batches, contiguous write positions, read-only positions and
  optional `wrote` flags. Definite aborts are no-ops; provisional observations from
  those aborts do not constrain state. Indeterminate outcomes cannot pass.
- Stored quiescent full-head rows and exact raw mutation-event order, using model
  snapshots built from the witness's recorded committed writes, not engine snapshots.
- Consistent engine version, source SHA and consecutive seeds throughout a stream.

The model supports the Rust checker's default limits: 64 operations, 64 steps per
operation, 8 MiB logical input charge, 1,024 model rows and 256 KiB logical model
charge. JSONL lines are bounded to 2 MiB; at most 100,000 records are accepted.
Input is streamed as plain JSONL or gzip, detected by gzip magic bytes. Duplicate
JSON fields, malformed bytes, truncated gzip, inconsistent metadata and empty
streams fail closed. Both the exact file hash and decompressed JSONL hash are
reported. A failure explicitly identifies a partial decompressed digest.

```sh
python3 -B verify-linearizability-traces.py /path/to/histories.jsonl.gz \
  --expected-sha EXACT_40_CHARACTER_SOURCE_SHA --expected-version 1.0.0 \
  --expected-first-seed 20261025 --expected-count 10000 \
  --report NEW-witness-validation.json

python3 -B test-linearizability-witness.py
```

Report destinations must be new files. A passing report states the actual record,
operation, model-snapshot and stored-head counts, file hashes and verifier hash.
It is **not full release qualification** and does not authenticate recorded
source metadata or establish that the recorder omitted no calls. Historical
predicate observations and quiescent query responses absent from the trace are
not inferred from phase counts or replayed by this tool. The live engine campaign
and its separate historical/corruption/crash qualification remain necessary.

The accompanying `development-witness-validation-final.json` checks the completed
**24-record development smoke trace**, not the 10,000-history challenge. Synthetic
unit controls are also separate from measured engine workload histories. They
reject false real-time witnesses, lost updates, partial rows/events, wrong receipt
metadata, uncertain outcomes and malformed or mixed-provenance streams.
