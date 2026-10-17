# Local search in the 0.6 preview candidate

`Database::search` returns a complete, bounded result at one committed position.
It works on the single-node database. Search neither creates a subscription nor
changes existing byte-key, whole-value, event, or replicated query contracts.
Run it again to see later commits.

## Predicates

- `JsonEquals` parses each value as JSON and follows 1–8 exact object-key
  segments. The selected value must be a scalar: string, number, boolean, or
  null. Missing paths, arrays, objects, malformed JSON, and non-JSON values do
  not match. A missing path does not equal null. Both the query scalar and stored
  scalar are parsed as `serde_json::Value` and compared by their serialized
  representation; this is not a schema or numeric coercion layer.
- `TextAll` treats a valid UTF-8 value as text. Each maximal run of Unicode
  alphanumeric characters is a word, lowercased with Rust's Unicode lowercase
  conversion. Every distinct query word must occur as a whole word, in any order.
  Repeated words add no condition. There is no phrase order, stemming, ranking,
  locale-specific collation, or search inside binary values.

Both predicates apply within a byte-key `KeyRange`. An empty prefix searches all
keys; `KeyRange::prefix(b"docs/")` excludes `docs-archive/`.

```rust
use polybase_engine::{Database, KeyRange, SearchPredicate, SearchQuery};

fn open_docs(db: &Database) -> polybase_engine::Result<()> {
    let result = db.search(SearchQuery {
        range: KeyRange::prefix(b"docs/"),
        predicate: SearchPredicate::JsonEquals {
            path: vec!["status".into()],
            value: serde_json::json!("open"),
        },
    })?;
    println!("committed position: {}", result.position);
    for (key, value) in result.entries {
        println!("{:?}: {:?}", key, value);
    }
    Ok(())
}
```

The local console has a separate **Search committed records** panel. Enter a
dot-separated object path such as `owner.name`, or a JSON array of path strings
if a key itself contains a dot. The JSON value field requires a literal such as
`"open"`, `42`, `true`, or `null`. Text mode takes search words. Results show the
commit position and whether the index or complete scan served the request. The
browser rejects a numeric literal that JavaScript would change while parsing;
use the HTTP API with the exact JSON number in that case.

The local loopback HTTP API accepts `POST /api/search` with JSON bodies:

```json
{"kind":"json","key_prefix":"646f63732f","path":["status"],"value":"open"}
```

```json
{"kind":"text","key_prefix":"646f63732f","text":"quick fox"}
```

`key_prefix` and returned `rows[].key`/`rows[].value` are lowercase hex bytes;
`position` is a decimal string. The reply also contains `indexed: true|false`.
The existing exact loopback Host/Origin and request-size rules apply. The
replicated console has no `/api/search` endpoint.

## Bounds and failure behavior

Defaults are a 16 MiB logical in-memory index charge, 4,096 result rows, and
2 MiB of returned key plus value bytes. The index cap can be configured up to
256 MiB or set to zero to force complete scans; configured result caps cannot
exceed 100,000 rows or 64 MiB. JSON paths allow at most eight
segments of 128 UTF-8 bytes each, and the serialized query scalar is at most
4,096 bytes. Text queries allow 4,096 UTF-8 bytes, eight distinct words, and
256 bytes per word. Values with too many index terms cause the entire index to
fall back to a scan; terms that cannot be queried under these limits are ignored.
These are logical charges and input limits, not a process RSS guarantee.

The index is derived in memory from the committed view on first use, then
updated before a new head becomes visible. It is not written to disk. If building
or updating exceeds its cap, search uses a complete bounded scan for the rest
of that open instance. Reopening may build it again. A result limit error returns
no partial result. Reopen strictly verifies canonical storage before search can
rebuild; it does not use an index to hide WAL or checkpoint damage.
