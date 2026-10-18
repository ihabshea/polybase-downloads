# Polybase local client

Typed HTTP client for a local Polybase console. This package contains compiled
ES modules and TypeScript declarations. It does not contain the database engine
or a hosted service. Requires Node.js 24 or newer and a separately installed
Polybase console; version 0.9.0 is the release qualification target.

The published registry SDK is **0.8.3**, qualified against console 0.8.2.
This checkout prepares the **0.9.0 Janus candidate**, which has not been
published to the registries. The install command below uses the published
SDK; Janus methods require building this candidate source or a verified
future 0.9.0 publication.

```sh
npm install @polymathbase/polybase-client@0.8.3
```

Start `polybase-console /path/to/database 7340`, then:

```js
import {Client, hex, unhex} from '@polymathbase/polybase-client';

const client = new Client('http://127.0.0.1:7340');
const read = await client.readRevision('tasks/1');
const receipt = await client.writeRevision(
  read.revision, JSON.stringify({status: 'open'}),
);
const page = await client.page({
  key_prefix: hex('tasks/'), predicate: 'json', value: '',
  json: {op: 'eq', path: ['status'], value: 'open'},
});
console.log(receipt.position, page.explain);
for (const row of page.rows) {
  console.log(new TextDecoder().decode(unhex(row.value)));
}
```

`readRevision` returns an opaque revision for a conditional `writeRevision`.
An HTTP 409 reports a stale revision. A transport timeout or cancellation can
leave a write's outcome uncertain: the server can still commit. The client never
automatically retries writes. Reconcile application state before another write.

Query pages have a captured position and an optional continuation cursor.
Retain the query and use `client.page(query, page.next, limit)` while `next` is
non-null. Keys and values in returned rows are lowercase hexadecimal bytes.
Positions are decimal strings; use `bigint`, never a JavaScript `number`, for
position arithmetic. Requests reject unsafe integer inputs before transport.

`subscribe(query)` captures initial rows and a token. Persist those together,
then consume `client.stream(session, savedToken, abortSignal)`. Apply each complete
page of commit transitions and persist its token atomically before requesting
the next page. On restart call `resume(savedToken)` and explicitly continue from
the last applied token. Delivery can repeat, tokens can expire, and the client
does not silently take a new snapshot. Streaming uses polling on consumer demand.

`search({kind: 'json', key_prefix: hex('tasks/'), path: ['status'], value: 'open'})`
and `search({kind: 'text', key_prefix: hex('notes/'), text: 'quick fox'})` call
`/api/search`: bounded current-head scalar equality or Unicode whole-word search,
without a subscription. This differs from `searchIndex`, which calls
`/api/index-search` for one named equality index, and from paginated typed queries.

`createIndex(name, prefix, path)` encodes its prefix as a JSON byte array because
the server's `index-create` route requires that format. Other key and
`key_prefix` wire fields use lowercase hex. The client handles this conversion.

Non-JSON HTTP errors retain their status in `ApiError.status` and response text
in `ApiError.body` (invalid UTF-8 is replaced). JSON error bodies stay parsed;
successful responses still require valid JSON.

The client supports explicit IPv4 loopback HTTP origins only, a 128 KiB request
bound, an 8 MiB response bound and a five-second request timeout. Keep the console
on loopback. Query optimizer estimates describe work units, not measured latency.

See the [Polybase documentation](https://base.polymathlabs.xyz/docs) for server
installation, limits and protocol guarantees. Client terms are in `LICENSE`.
The public [client source](https://github.com/ihabshea/polybase-downloads/tree/main/clients/typescript)
and release tags allow comparison with the registry archive; the engine is private.

Janus adds `getAsOf(position, key)`, `queryAsOf(position, query, cursor, limit)`
and `searchAsOf(position, searchQuery, limit)`. Positions are `bigint` inputs and
canonical decimal strings on the wire. `queryAsOf` also accepts optional explicit
byte-key bounds, for example `{start: {included: hex('tasks/a')}, end: {excluded:
hex('tasks/z')}}`. `explainAsOf` executes the same historical query path.

Historical replies provide `JanusExplain`: chosen strategy, estimated rows,
measured examined/returned rows, reasons, captured position, timings, candidates,
and bytes examined. `execution_stats.planning_rows` counts examined index-definition
metadata rows (plus current-head definition-coverage work); byte counters describe logical data examined, not disk I/O.
Historical scalar search preserves `SearchQuery` semantics;
paginated typed JSON equality treats `1` and `1.0` as equal. Historical search
returns the complete result within `limit`, reports a capacity error if it cannot
fit, and always has `next: null`; query pages support cursors.

Keep the original position and query with a historical cursor. HTTP 410
`history_expired` requires an application choice; the SDK never switches to a
current-head read. An absent key succeeds with `value: null`, while an empty
query succeeds with `rows: []`. `searchDiagnostics` exposes a required typed explain report for current-head
search; the old `search` response type adds it as an optional field. New Janus
methods require a 0.9 server. Existing
methods and compiled package exports remain backward compatible.
