# Polybase local client

Bounded synchronous HTTP client for a local Polybase console. This crate contains
the standalone client and depends on `serde` and `serde_json`. It does not contain
the private database engine or a hosted service. Requires Rust 1.89 or newer and
a separately installed Polybase console; version 0.8.2 is the release
qualification target.

```sh
cargo add polybase-client@0.8.3
```

Start `polybase-console /path/to/database 7340`, then:

```rust
use polybase_client::{Client, Query};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::new("127.0.0.1:7340".parse()?)?;
    let read = client.read_revision(b"tasks/1")?;
    let receipt = client.write_revision(
        &read.revision, Some(br#"{"status":"open"}"#),
    )?;
    let page = client.page(&Query::all(b"tasks/"), None, 64)?;
    println!("{} {}", receipt.position, page.rows.len());
    Ok(())
}
```

`read_revision` returns an opaque revision for a conditional `write_revision`.
`Error::Api { status: 409, .. }` reports a stale revision. A transport timeout can
leave a write's outcome uncertain: the server can still commit. The client never
automatically retries writes. Reconcile application state before another write.

Query pages have a captured position and an optional continuation cursor. Keep
the query and pass `page.next.as_deref()` to subsequent `page` calls until it is
`None`. Keys and values in returned rows are lowercase hexadecimal bytes; use
`unhex` to decode them. Positions are decimal strings.

`subscribe` captures initial rows and a token. Persist those together. `poll`
takes the application's last applied token explicitly: apply complete commit
transitions and atomically persist rows and the returned token before advancing.
On restart call `resume` with the saved token, then pass its returned
`ResumedSession` and the saved token to `poll`. Resume returns session identity
without taking another snapshot. Both initial and resumed sessions work with
`poll` and `unsubscribe`. Delivery can repeat, tokens can
expire, and the client does not silently take a new snapshot. `Client::call`
provides serde-typed access to other documented routes.

`verify_backup`, `create_index`, `indexes`, `search_index`, `drop_index` and
`compaction_advice` provide the same named maintenance/index routes as the
TypeScript client. `create_index` serializes its prefix bytes as a JSON byte
array because the server's `index-create` route requires that format. Other key
and `key_prefix` wire fields use lowercase hex.

`search(&SearchQuery::Json { .. })` and `search(&SearchQuery::Text { .. })` call
`/api/search`: bounded current-head scalar equality or Unicode whole-word search,
without a subscription. This differs from `search_index`, which calls
`/api/index-search` for one named equality index, and from paginated typed queries.
Search prefixes are lowercase hex strings, produced with `hex`.

Non-JSON HTTP error responses retain their status in `Error::Api`; `body` is a
JSON string containing the response text (invalid UTF-8 is replaced). Successful
responses still require valid JSON.

The client supports IPv4 loopback only, uses blocking standard-library TCP,
bounds requests to 128 KiB and responses to 8 MiB, and sets five-second connect,
read and write socket timeouts. A read timeout is a per-socket-operation timeout,
not a deadline for the entire response. Keep the console on loopback.

See the [Polybase documentation](https://base.polymathlabs.xyz/docs) for server
installation, limits and protocol guarantees. Client terms are in `LICENSE`.
The public [client source](https://github.com/ihabshea/polybase-downloads/tree/main/clients/rust)
and release tags allow comparison with the registry archive; the engine is private.
