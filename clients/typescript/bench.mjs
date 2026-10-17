// Run only against a disposable benchmark console; existing prefixes are refused.
import assert from "node:assert/strict";
import {performance} from "node:perf_hooks";
import {Client,hex} from "./client.ts";
const [base,prefix,rawCount]=process.argv.slice(2);const count=Number(rawCount);
assert.ok(Number.isInteger(count) && count>0 && count<=128);
const client=new Client(base);const query={key_prefix:hex(prefix),predicate:"any",value:""};
const session=await client.subscribe(query);assert.equal(session.rows.length,0);
let started=performance.now();
for(let i=0;i<count;i++) {
  const key=prefix+String(i).padStart(4,"0");const read=await client.readRevision(key);assert.equal(read.value,null);
  const receipt=await client.writeRevision(read.revision,JSON.stringify({client:"typescript",n:i}));assert.equal(receipt.durable,true);
}
const revision_read_write_us=Math.round((performance.now()-started)*1000);
started=performance.now();const page=await client.page(query,null,128);assert.equal(page.rows.length,count);const page_us=Math.round((performance.now()-started)*1000);
started=performance.now();const delta=await client.poll(session,session.token);assert.equal(delta.commits.length,count);const poll_us=Math.round((performance.now()-started)*1000);
await client.unsubscribe(session,delta.token);
console.log(JSON.stringify({client:"typescript",records:count,revision_read_write_us,page_us,poll_us,correctness_verified:true}));
