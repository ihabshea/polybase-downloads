/** Local loopback client. Writes are never automatically retried. */
export type Scalar = null | boolean | number | string;
export type JsonPredicate =
  | {op: "eq" | "ne" | "lt" | "le" | "gt" | "ge"; path: string[]; value: Scalar}
  | {op: "exists"; path: string[]; present: boolean}
  | {op: "type"; path: string[]; kind: "null" | "boolean" | "number" | "string" | "array" | "object"}
  | {op: "prefix"; path: string[]; value: string}
  | {op: "all" | "any"; predicates: JsonPredicate[]}
  | {op: "not"; predicate: JsonPredicate};
export type Query = {key_prefix: string; predicate: "any" | "equals" | "prefix"; value: string}
  | {key_prefix: string; predicate: "json"; value: ""; json: JsonPredicate};
export interface Row {key: string; value: string}
/** A bounded current-head search, separate from named indexes and query pages. */
export type SearchQuery = {kind: "json"; key_prefix: string; path: string[]; value: Scalar}
  | {kind: "text"; key_prefix: string; text: string};
export interface SearchResult {position: string; indexed: boolean; rows: Row[]; explain?: JanusExplain}
export interface ExplainedSearchResult extends SearchResult {explain: JanusExplain}
export interface OptimizerAlternative {
  strategy: "scan" | "index_lookup" | "index_intersection" | "index_union";
  index_names: string[]; estimated_candidates: number; estimated_work: number;
}
export interface OptimizerExplain {
  strategy: OptimizerAlternative["strategy"] | "retained_history_scan"; initial_strategy: OptimizerAlternative["strategy"] | "retained_history_scan";
  index_names: string[]; alternatives: OptimizerAlternative[];
  estimated_work: number; estimated_range_rows: number; statistics_epoch: number | null;
  total_live_records: number; statistics_rows: number; definition_coverage: {name: string; prefix: number[]; records: number}[];
  term_cardinalities: {index_name: string; path: string[]; value: Scalar; cardinality: number}[];
  actual_work: {posting_steps: number; canonical_lookups: number; predicate_evaluations: number; scan_rows: number; restarts: number};
  phase_timings_micros: {planning: number; index_execution: number; scan_execution: number};
  replan_reason: string | null;
  calibration: {enabled: boolean; samples: number; lookup_weight_units: number};
}
export interface QueryExplain {
  plan: string; position: string; scanned_records: number; scanned_rows: number;
  matched_rows: number; returned_rows: number; elapsed_micros: number;
  execution_plan: {kind: "scan"} | {kind: "index_lookup"; index_name: string};
  index_name: string | null; fallback_reason: string | null; candidate_count: number;
  planning_rows: number; index_build_rows: number; index_build_micros: number; total_rows_examined: number;
  /** Added in 0.8.2; absent in responses from older servers. Estimated work is not elapsed time. */
  optimizer?: OptimizerExplain;
  /** Added by Janus servers; older server responses omit these fields. */
  chosen_plan?: JanusExplain["chosen_plan"]; estimated_rows?: number;
  actual_rows?: JanusExplain["actual_rows"]; plan_reason?: string;
  history_position?: string; execution_stats?: JanusExplain["execution_stats"];
}
/** Janus diagnostics use measured counters separately from estimated row work. */
export interface JanusExplain {
  chosen_plan: "index" | "range_scan" | "full_scan" | "historical_replay";
  estimated_rows: number;
  actual_rows: {examined: number; returned: number};
  plan_reason: string;
  fallback_reason: string | null;
  history_position: string;
  execution_stats: {
    elapsed_micros: number; planning_micros: number; planning_rows: number; execution_micros: number;
    replay_micros: number; index_build_micros: number; candidates: number;
    /** Logical canonical/index-build bytes plus verified WAL bytes, not disk I/O. */
    bytes_examined: number; returned_bytes: number; base_rows: number;
    replayed_commits: number; replayed_mutations: number; index_build_rows: number;
    query_rows_examined: number; cache_hit: boolean; index_used: boolean;
    cache_bytes: number; index_bytes: number; history_floor: string; cache_head: string;
  };
}
/** Byte-key bounds are lowercase hex. Null means unbounded. */
export type KeyBound = {included: string} | {excluded: string} | null;
export interface KeyRange {start: KeyBound; end: KeyBound}
export interface HistoricalPoint {position: string; value: string | null; explain: JanusExplain}
export interface HistoricalPage {position: string; rows: Row[]; next: string | null; explain: JanusExplain}
export interface Page {position: string; rows: Row[]; next: string | null; explain: QueryExplain}
export interface Session {id: string; instance: string; token: string; position: string; rows: Row[]}
export interface Change {key: string; before: string | null; after: string | null}
export interface StreamPage {commits: {position: string; changes: Change[]}[]; token: string; position: string; head: string; floor: string}
export interface RevisionRead {value: string | null; revision: string; position: string}
export interface Receipt {position: string; durable: boolean; wrote: boolean}
export class ApiError extends Error {
  status: number; body: unknown;
  constructor(status: number, body: unknown) {super(`Polybase HTTP ${status}: ${JSON.stringify(body)}`);this.status=status;this.body=body;}
}
export const hex = (value: Uint8Array | string): string => [...(typeof value === "string" ? new TextEncoder().encode(value) : value)].map(b=>b.toString(16).padStart(2,"0")).join("");
export function unhex(value: string): Uint8Array {
  if (!/^(?:[0-9a-f]{2})*$/.test(value)) throw new Error("invalid hex");
  return Uint8Array.from(value.match(/../g) || [], b=>Number.parseInt(b,16));
}
function safeNumbers(value: unknown, depth = 0): void {
  if (depth > 64) throw new Error("request nesting exceeds 64");
  if (typeof value === "number" && (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value)))) throw new Error("unsafe JSON number; use strings for exact large integers");
  if (value && typeof value === "object") for (const child of Object.values(value)) safeNumbers(child,depth+1);
}
export class Client {
  readonly base: string;
  constructor(base = "http://127.0.0.1:7340") {
    if (!/^http:\/\/127\.0\.0\.1:[1-9][0-9]*$/.test(base) || Number(new URL(base).port)>65535) throw new Error("use an IPv4 loopback origin with an explicit port");
    this.base=base;
  }
  async call<T>(route: string, body: unknown, signal?: AbortSignal): Promise<T> {
    if (!/^[a-z-]+$/.test(route)) throw new Error("invalid route");
    safeNumbers(body);
    const payload=JSON.stringify(body);
    if (new TextEncoder().encode(payload).length>128*1024) throw new Error("request exceeds 128 KiB");
    const response=await fetch(`${this.base}/api/${route}`,{method:"POST",headers:{"Content-Type":"application/json",Origin:this.base},body:payload,signal:signal ? AbortSignal.any([signal,AbortSignal.timeout(5000)]) : AbortSignal.timeout(5000),redirect:"error"});
    const reader=response.body?.getReader();
    if (!reader) {
      if (!response.ok) throw new ApiError(response.status, "");
      throw new Error("missing response body");
    }
    const chunks: Uint8Array[]=[];let size=0;
    try {
      while (true) {const {done,value}=await reader.read();if(done) break;size+=value.length;if(size>8*1024*1024) throw new Error("response exceeds 8 MiB");chunks.push(value);}
    } finally {await reader.cancel();reader.releaseLock();}
    const all=new Uint8Array(size);let offset=0;for(const chunk of chunks){all.set(chunk,offset);offset+=chunk.length;}
    const text=new TextDecoder("utf-8",{fatal:response.ok}).decode(all);
    let result: unknown;
    try {result=JSON.parse(text);} catch (error) {
      if (response.ok) throw error;
      result=text;
    }
    if (!response.ok) throw new ApiError(response.status,result);
    return result as T;
  }
  page(query: Query,cursor: string | null = null,limit = 128,forceScan = false): Promise<Page> {return this.call("query-page",{query,cursor,limit,...(forceScan ? {force_scan:true} : {})});}
  /** Read retained commit position exactly; no implicit resnapshot on expiry. */
  getAsOf(position: bigint,key: Uint8Array | string): Promise<HistoricalPoint> {return this.call("as-of-get",{position:position.toString(),key:hex(key)});}
  queryAsOf(position: bigint,query: Query,cursor: string | null = null,limit = 128,range?: KeyRange): Promise<HistoricalPage> {return this.call("as-of-query",{position:position.toString(),query,cursor,limit,...(range ? {range} : {})});}
  explainAsOf(position: bigint,query: Query,cursor: string | null = null,limit = 128,range?: KeyRange): Promise<HistoricalPage> {return this.call("as-of-explain",{position:position.toString(),query,cursor,limit,...(range ? {range} : {})});}
  searchAsOf(position: bigint,query: SearchQuery,limit = 128): Promise<HistoricalPage> {return this.call("as-of-search",{position:position.toString(),query,limit});}
  readRevision(key: Uint8Array | string): Promise<RevisionRead> {return this.call("read-revision",{key:hex(key)});}
  writeRevision(revision: string,value: Uint8Array | string | null): Promise<Receipt> {return this.call("write-revision",{revision,value:value===null ? null : hex(value)});}
  subscribe(query: Query): Promise<Session> {return this.call("query",query);}
  resume(token: string): Promise<{id:string;instance:string}> {return this.call("resume",{token});}
  poll(session: Pick<Session,"id"|"instance">,token: string,signal?: AbortSignal): Promise<StreamPage> {return this.call("poll",{id:session.id,instance:session.instance,token},signal);}
  unsubscribe(session: Pick<Session,"id"|"instance">,token: string): Promise<unknown> {return this.call("unsubscribe",{id:session.id,instance:session.instance,token});}
  snapshotAt(position: bigint): Promise<{position:string;rows:Row[]}> {return this.call("snapshot-at",{position:position.toString()});}
  backup(directory: string): Promise<unknown> {return this.call("backup",{directory});}
  verifyBackup(directory: string): Promise<unknown> {return this.call("verify-backup",{directory});}
  /** The index-create route requires prefix bytes as a JSON array, not hex. */
  createIndex(name: string,prefix: Uint8Array | string,path: string[]): Promise<unknown> {return this.call("index-create",{name,prefix:Array.from(typeof prefix==="string" ? new TextEncoder().encode(prefix) : prefix),path});}
  indexes(): Promise<unknown> {return this.call("index-list",{});}
  searchIndex(name: string,value: Scalar): Promise<{position:string;indexed:boolean;rows:Row[]}> {return this.call("index-search",{name,value});}
  dropIndex(name: string): Promise<unknown> {return this.call("index-drop",{name});}
  search(query: SearchQuery): Promise<SearchResult> {return this.call("search",query);}
  searchDiagnostics(query: SearchQuery): Promise<ExplainedSearchResult> {return this.call("search",query);}
  compactionAdvice(retainCommits: bigint): Promise<unknown> {return this.call("compaction-advice",{retain_commits:retainCommits.toString()});}
  /** Yield one complete page at a time. Persist rows and token before requesting another.
   * A cancellation after a write is not an abort. No transport retry or implicit resnapshot. */
  async *stream(session: Pick<Session,"id"|"instance">,appliedToken: string,signal?: AbortSignal): AsyncGenerator<StreamPage> {
    let token=appliedToken;
    try {
      while (!signal?.aborted) {
        const page=await this.poll(session,token,signal);
        if (BigInt(page.position)<BigInt(tokenPosition(token))) throw new Error("stream cursor regressed");
        if (page.token!==token) {yield page;token=page.token;}
        else await new Promise<void>(resolve=>{const done=()=>{clearTimeout(timer);signal?.removeEventListener("abort",done);resolve();};const timer=setTimeout(done,25);signal?.addEventListener("abort",done,{once:true});});
      }
    } finally {await this.unsubscribe(session,token).catch(()=>{});}
  }
}
function tokenPosition(token: string): bigint {
  const bytes=unhex(token);
  if (bytes.length<36 || new TextDecoder().decode(bytes.subarray(0,8))!=="ENDBTOK1") throw new Error("invalid local cursor");
  return new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength).getBigUint64(24,true);
}
