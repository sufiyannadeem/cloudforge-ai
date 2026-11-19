import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";
import * as metrics from "../src/lib/platform-reliability.ts";
const require = createRequire(import.meta.url);
function load(path, aliases) {
  const code = ts.transpileModule(readFileSync(new URL(path,import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const exports={};Function("require","exports",code)((name)=>Object.hasOwn(aliases,name)?aliases[name]:require(name),exports);return exports;
}
function payload(value="2", time=1000, namespace="cloudforge") {return {status:"success",data:{resultType:"vector",result:[{metric:{namespace,deployment:"project-service"},value:[time,value]}]}};}
test("scaling evidence keeps measured zero and rejects stale, invalid and foreign data",()=>{
  assert.equal(metrics.reliabilityValues(payload("0"),"deployment",1000).get("project-service"),0);
  for(const data of [payload("NaN"),payload("-1"),payload("1.5"),payload(""),payload("2",900),payload("2",1010),payload("2",1000,"other"),{status:"error"}]) assert.equal(metrics.reliabilityValues(data,"deployment",1000).size,0);
  const duplicate=payload();duplicate.data.result.push(duplicate.data.result[0]);assert.equal(metrics.reliabilityValues(duplicate,"deployment",1000).size,0);
  for(const definition of Object.values(metrics.RELIABILITY_QUERIES)) {assert.match(definition.query,/namespace="cloudforge"/);assert.match(definition.query,/timestamp\(/);assert.doesNotMatch(definition.query,/or vector\(0\)/);}
  assert.match(metrics.RELIABILITY_QUERIES.available.query,/kube_deployment_status_observed_generation/);
});
test("reliability endpoint checks verified operator identity before any global query",async(t)=>{
  const {NextRequest}=require("next/server");let role="developer",calls=0;
  const {GET}=load("../src/app/api/platform-reliability/route.ts",{
    "@/lib/platform-reliability":metrics,"@/lib/auth":{SESSION_COOKIE:"cf_session",verifySessionToken:async(token)=>token==="valid"?{role}:null},
  });
  t.mock.method(globalThis,"fetch",async(url)=>{calls++;assert.match(new URL(url).searchParams.get("query"),/namespace="cloudforge"/);return Response.json({status:"success",data:{resultType:"vector",result:[]}});});
  const req=(cookie=true,query="")=>new NextRequest("https://console.example/api/platform-reliability"+query,{headers:{"x-cloudforge-role":"platform-engineer",...(cookie?{cookie:"cf_session=valid"}:{})}});
  assert.equal((await GET(req(false))).status,401);assert.equal((await GET(req())).status,403);assert.equal(calls,0);
  for(role of ["sre","platform-engineer"]){const response=await GET(req());assert.equal(response.status,200);assert.equal(response.headers.get("cache-control"),"private, no-store");const data=await response.json();assert.equal(data.rows.length,6);assert.ok(data.rows.every(row=>row.desired===null && row.available===null));}
  const previous=calls;assert.equal((await GET(req(true,"?namespace=other"))).status,400);assert.equal(calls,previous);
});
