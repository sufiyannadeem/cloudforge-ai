import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { serviceAssertion } from "../src/lib/service-identity.ts";
import * as csrf from "../src/lib/csrf.ts";
const require = createRequire(import.meta.url);
function load(path, aliases = {}) {
  const { outputText } = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  const exports = {};
  Function("require", "exports", outputText)((name) => Object.hasOwn(aliases, name) ? aliases[name] : require(name), exports);
  return exports;
}
test("only operators viewing a ready paused preview see promotion, with explicit consent", () => {
  for (const [operator, ready, paused, allowed, phase = "Paused"] of [[true,true,true,true],[false,true,true,false],[true,false,true,false],[true,true,false,false],[true,true,true,false,"Degraded"]]) {
    const values = [{ uid:"uid",resource_version:"42",phase,preview_service:"preview",preview_ready:ready,promotion_required:paused,traffic_mode:"active/preview services" },[],false,false,""];
    const { default: Controls } = load("../src/components/deployments/RolloutControls.tsx", { react:{useState:()=>[values.shift(),()=>{}]} });
    const html = renderToStaticMarkup(createElement(Controls,{deployment:{id:"deployment",status:"running",image:"approved-image"},operator,csrfHeaders:()=>({})}));
    assert.equal(html.includes("Approve and promote preview"),allowed);
    if (allowed) { assert.match(html,/type="checkbox"/); assert.match(html,/disabled=""[^>]*>Approve and promote preview/); assert.match(html,/requester cannot self-approve/); }
  }
});
test("promotion proxy preserves session RBAC, CSRF and exact signed body binding", async (t) => {
  const { NextRequest } = require("next/server");
  const keyName="CLOUDFORGE_FRONTEND_DEPLOYMENT_KEY",old=process.env[keyName];
  process.env[keyName]="test-only-deployment-approval-key-32-bytes";
  t.after(()=>{if(old===undefined)delete process.env[keyName];else process.env[keyName]=old;});
  let role="platform-engineer",calls=0;
  const body=JSON.stringify({uid:"uid",resource_version:"42",approve:true});
  const { POST }=load("../src/app/api/proxy/[service]/[...path]/route.ts",{
    "@/lib/service-identity":{serviceAssertion},"@/lib/server-config":{serviceConfig:{deployment:"https://deployment.example"}},"@/lib/csrf":csrf,
    "@/lib/auth":{CSRF_COOKIE:"cf_csrf",SESSION_COOKIE:"cf_session",verifySessionToken:async(token)=>token==="valid"?{sub:"reviewer",role,csrf:"csrf",exp:Math.floor(Date.now()/1000)+25}:null},
  });
  t.mock.method(globalThis,"fetch",async(url,options)=>{
    calls++;assert.equal(String(url),"https://deployment.example/api/v1/deployments/deployment/promote");
    const claims=JSON.parse(Buffer.from(options.headers.get("X-CloudForge-Identity").split(".")[0],"base64url"));
    assert.equal(claims.body,createHash("sha256").update(body).digest("hex"));assert.equal(claims.role,"platform-engineer");assert.equal(claims.sub,"reviewer");
    assert.equal(options.headers.get("X-CloudForge-Role"),null);return Response.json({status:"submitted"},{status:202});
  });
  const request=(authenticated=true,withCSRF=true)=>new NextRequest("https://console.example/api/proxy/deployment/api/v1/deployments/deployment/promote",{
    method:"POST",body,headers:{host:"console.example",origin:"https://console.example","content-type":"application/json","x-cloudforge-role":"platform-engineer",...(authenticated?{cookie:"cf_session=valid; cf_csrf=csrf"}:{}),...(withCSRF?{"x-csrf-token":"csrf"}:{})},
  });
  const context={params:Promise.resolve({service:"deployment",path:["api","v1","deployments","deployment","promote"]})};
  assert.equal((await POST(request(),context)).status,202);assert.equal(calls,1);
  assert.equal((await POST(request(true,false),context)).status,403);assert.equal((await POST(request(false),context)).status,401);
  for(role of ["developer","sre"])assert.equal((await POST(request(),context)).status,403);
  assert.equal(calls,1);
});
