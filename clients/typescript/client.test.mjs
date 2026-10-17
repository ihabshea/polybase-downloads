import assert from "node:assert/strict";
import {test} from "node:test";
import {mkdtemp,rm,mkdir} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {spawn} from "node:child_process";
import {once} from "node:events";
import {createServer} from "node:net";
import {createServer as createHttpServer} from "node:http";
import {fileURLToPath} from "node:url";
const {Client,ApiError,hex,unhex} = await import(process.env.POLYBASE_CLIENT_MODULE || "./client.ts");

test("client validates loopback addresses, hex and unsafe numeric inputs",async()=>{
  assert.throws(()=>new Client("https://example.com"));assert.throws(()=>unhex("a"));assert.throws(()=>unhex("AA"));
  assert.equal(new TextDecoder().decode(unhex(hex("مرحبا"))),"مرحبا");
  await assert.rejects(new Client().call("query",{n:9007199254740992}),/unsafe JSON/);
});

test("HTTP errors preserve status and non-JSON text; successful replies still require JSON",async()=>{
  const replies=[
    [500,"upstream panic","upstream panic"], [503,"",""],
    [502,Buffer.from([98,97,100,32,255]),"bad \ufffd"],
    [409,'{"error":"conflict"}',{error:"conflict"}], [200,"invalid success"],
  ];
  let calls=0;
  const server=createHttpServer((request,response)=>{const [status,body]=replies[calls++];request.resume();response.writeHead(status);response.end(body);});
  server.listen(0,"127.0.0.1");await once(server,"listening");
  try {
    const client=new Client(`http://127.0.0.1:${server.address().port}`);
    for(const [status,,expected] of replies.slice(0,-1)) {
      await assert.rejects(client.readRevision("docs/a"),error=>{
        assert.ok(error instanceof ApiError);assert.equal(error.status,status);assert.deepEqual(error.body,expected);return true;
      });
    }
    await assert.rejects(client.readRevision("docs/a"),SyntaxError);
    assert.equal(calls,replies.length,"failed requests must not be retried");
  } finally {server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});

test("TypeScript client exercises real HTTP queries, revisions, streaming, backup and recovery",{timeout:30000},async()=>{
  const root=await mkdtemp(join(tmpdir(),"polybase-ts-"));const db=join(root,"db");await mkdir(db);
  const listener=createServer();listener.listen(0,"127.0.0.1");await once(listener,"listening");const port=listener.address().port;await new Promise(resolve=>listener.close(resolve));
  const binary=process.env.POLYBASE_CONSOLE_BIN || resolve(fileURLToPath(new URL("../../target/debug/polybase-console",import.meta.url)));
  let child;
  const start=async()=>{
    child=spawn(binary,[db,String(port)],{stdio:["ignore","pipe","pipe"]});let log="";child.stderr.on("data",chunk=>log+=chunk);
    for(let i=0;i<200;i++) {
      if(child.exitCode!==null) throw new Error(`console exited: ${log}`);
      try {const r=await fetch(`http://127.0.0.1:${port}/api/health`);if(r.ok)return;}catch{}
      await new Promise(resolve=>setTimeout(resolve,10));
    }
    throw new Error(`startup deadline: ${log}`);
  };
  const stop=async()=>{if(child && child.exitCode===null){const exited=once(child,"exit");child.kill("SIGTERM");await exited;}};
  try {
    await start();const c=new Client(`http://127.0.0.1:${port}`);
    const query={key_prefix:hex("docs/"),predicate:"json",value:"",json:{op:"eq",path:["status"],value:"open"}};
    const session=await c.subscribe(query);assert.deepEqual(session.rows,[]);
    const initial=await c.readRevision("docs/a");const receipt=await c.writeRevision(initial.revision,'{"status":"open"}');assert.equal(receipt.durable,true);
    await assert.rejects(c.writeRevision(initial.revision,"stale"),e=>e instanceof ApiError && e.status===409);
    const stream=c.stream(session,session.token);const event=await stream.next();assert.equal(event.value.commits[0].changes.length,1);const applied=event.value.token;await stream.return();
    const resumed=await c.resume(applied);const rev=await c.readRevision("docs/a");await c.writeRevision(rev.revision,'{"status":"closed"}');
    const delta=await c.poll(resumed,applied);assert.equal(delta.commits[0].changes[0].after,null);await c.unsubscribe(resumed,delta.token);
    for(const name of ["b","c","d"]) {const r=await c.readRevision(`docs/${name}`);await c.writeRevision(r.revision,'{"status":"open"}');}
    const first=await c.page(query,null,1);assert.equal(first.rows.length,1);assert.ok(first.next);
    const r=await c.readRevision("docs/c");await c.writeRevision(r.revision,'{"status":"closed"}');
    const second=await c.page(query,first.next,1);assert.equal(second.position,first.position);assert.equal(second.rows[0].key,hex("docs/c"));
    assert.equal(second.explain.plan,"retained_history_scan");
    await c.createIndex("status","docs/",["status"]);assert.equal((await c.searchIndex("status","open")).rows.length,2);
    // Keep this compatibility probe selective under the 0.8.2 cost model.
    for(let i=0;i<20;i++) {const r=await c.readRevision(`docs/nonmatch-${i}`);await c.writeRevision(r.revision,'{"status":"closed"}');}
    const planned=await c.page(query);const forced=await c.page(query,null,128,true);
    assert.equal((await c.search({kind:"json",key_prefix:hex("docs/"),path:["status"],value:"open"})).rows.length,2);
    assert.equal((await c.search({kind:"text",key_prefix:hex("docs/"),text:"open"})).rows.length,2);
    assert.equal(planned.explain.plan,"index_lookup");assert.equal(planned.explain.index_name,"status");assert.equal(planned.explain.candidate_count,2);assert.equal(planned.explain.optimizer.strategy,"index_lookup");assert.equal(String(planned.explain.optimizer.statistics_epoch),planned.position);assert.deepEqual(planned.rows,forced.rows);assert.equal(forced.explain.fallback_reason,"forced_scan");
    const explained=await c.call("explain",{query,cursor:null,limit:128});assert.deepEqual(explained.rows,planned.rows);assert.equal(explained.explain.plan,planned.explain.plan);
    const backup=join(root,"backup");assert.equal((await c.backup(backup)).verified,true);assert.equal((await c.verifyBackup(backup)).verified,true);
    assert.equal((await c.snapshotAt(BigInt(receipt.position))).rows.length,1);assert.equal((await c.compactionAdvice(100n)).suggested_floor,"0");
    await stop();await start();assert.equal((await c.page(query,first.next,1)).rows[0].key,hex("docs/c"));assert.equal((await c.indexes()).indexes.length,1);
    await c.dropIndex("status");assert.equal((await c.indexes()).indexes.length,0);
  } finally {await stop();await rm(root,{recursive:true,force:true});}
});
