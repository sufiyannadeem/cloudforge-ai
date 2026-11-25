import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createHmac, createHash } from "node:crypto";
import ts from "typescript";
import { serviceAssertion } from "../src/lib/service-identity.ts";
import * as csrf from "../src/lib/csrf.ts";
import { navigationFor, selectAuthorizedProject } from "../src/lib/role-access.ts";
const require = createRequire(import.meta.url);
function load(path, aliases) {
  const { outputText } = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    fileName: path,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  });
  const exports = {};
  Function("require", "exports", outputText)((id) => Object.hasOwn(aliases,id) ? aliases[id] : require(id),exports);
  return exports;
}

test("all roles reach scoped workspaces; foreign project selection never falls back", () => {
  for (const role of ["platform-engineer","sre","developer"]) {
    const links=navigationFor(role).flatMap(({items})=>items.map(({href})=>href));
    for (const href of ["/agent","/drift","/project-costs"]) assert.ok(links.includes(href));
  }
  assert.equal(selectAuthorizedProject([{id:"own"}],"foreign"),undefined);
});

test("real proxy enforces roles, CSRF, signed scope and backend denials for critical workflows", async (t) => {
  const { NextRequest }=require("next/server");
  const services=["project","infrastructure","deployment","aiops","finops"];
  const key="fixture-only-frontend-key-32-bytes-long";
  for (const service of services) {
    const name=`CLOUDFORGE_FRONTEND_${service.toUpperCase()}_KEY`;
    const previous=process.env[name];process.env[name]=`${key}-${service}`;
    t.after(()=>{if(previous===undefined)delete process.env[name];else process.env[name]=previous;});
  }
  let role="developer",calls=0;
  t.mock.method(globalThis,"fetch",async(url,options)=>{
    calls++;
    const token=options.headers.get("X-CloudForge-Identity");
    const [payload,signature]=token.split(".");
    assert.equal(signature,createHmac("sha256",process.env[`CLOUDFORGE_FRONTEND_${JSON.parse(Buffer.from(payload,"base64url")).aud.toUpperCase()}_KEY`]).update(payload).digest("hex"));
    const claims=JSON.parse(Buffer.from(payload,"base64url"));
    assert.equal(claims.role,role);assert.equal(claims.sub,"alice");
    assert.equal(claims.target,new URL(url).pathname+new URL(url).search);
    if (claims.aud === "aiops" && options.method === "POST" && String(url).includes("/remediation/")) {
      assert.equal(claims.body, createHash("sha256").update(Buffer.from(options.body ?? new ArrayBuffer(0))).digest("hex"));
    }
    // Backend fixture denies foreign objects, and rejects stale independent approvals.
    if (String(url).includes("foreign")) return Response.json({error:{message:"Not found"}},{status:404});
    if (String(url).endsWith("/promote")) return Response.json({error:{message:"Approval revision changed"}},{status:409});
    return Response.json({status:"unavailable"});
  });
  const proxy=load("../src/app/api/proxy/[service]/[...path]/route.ts",{
    "@/lib/service-identity":{serviceAssertion},"@/lib/csrf":csrf,
    "@/lib/server-config":{serviceConfig:Object.fromEntries(services.map(s=>[s,`https://${s}.example`]))},
    "@/lib/auth":{SESSION_COOKIE:"cf_session",CSRF_COOKIE:"cf_csrf",verifySessionToken:async(token)=>token==="verified"?{sub:"alice",role,csrf:"csrf-value",exp:Math.floor(Date.now()/1000)+25}:null},
  });
  async function request(service,path,method="GET",extra={}) {
    const request=new NextRequest(`https://console.example/api/proxy/${service}/${path}`,{
      method,headers:{host:"console.example",origin:"https://console.example",cookie:"cf_session=verified; cf_csrf=csrf-value","X-CSRF-Token":"csrf-value","X-CloudForge-Role":"platform-engineer",...extra},
    });
    return proxy[method](request,{params:Promise.resolve({service,path:path.split("/")})});
  }
  for (role of ["developer","sre","platform-engineer"]) {
    for (const [service,path] of [["deployment","api/v1/deployments/foreign/diagnostics"],["infrastructure","api/v1/resources/foreign/drift"],["finops","api/v1/finops/projects/foreign/costs"]]) {
      assert.equal((await request(service,path)).status,404);
    }
    const before=calls;
    const admin=await request("project","admin/accounts");
    assert.equal(admin.status,role==="platform-engineer"?200:403);
    if(role!=="platform-engineer") assert.equal(calls,before);
    assert.equal((await request("infrastructure","api/v1/resources/own/apply","POST")).status,role==="platform-engineer"?200:403);
    assert.equal((await request("infrastructure","api/v1/resources/own/plan","POST")).status,role==="sre"?403:200);
    assert.equal((await request("deployment","api/v1/deployments/own/promote","POST")).status,role==="platform-engineer"?409:403);
    assert.equal((await request("deployment","api/v1/deployments/own/diagnostics","POST",{"X-CSRF-Token":"wrong"})).status,403);
    assert.equal((await request("aiops","api/v1/incidents/own/knowledge")).status,role==="developer"?403:200);
    for (const action of ["approve", "execute"]) assert.equal((await request("aiops",`api/v1/incidents/own/remediation/proposal/${action}`,"POST")).status,role==="platform-engineer"?200:403);
    for (const action of ["reject", "alternative"]) assert.equal((await request("aiops",`api/v1/incidents/own/remediation/proposal/${action}`,"POST")).status,role==="developer"?403:200);
  }
});


test("Agent and Drift pages bind API evidence to the selected authorized project for every role", async () => {
  const React=require("react");
  const {renderToStaticMarkup}=require("react-dom/server");
  for (const role of ["platform-engineer","sre","developer"]) {
    for (const mode of ["agent","drift"]) {
      let calls=0;
      const {default:Workspace}=load("../src/components/workspaces/ProjectWorkspace.tsx",{
        "next/link":{default:({children,href})=>React.createElement("a",{href},children)},
        "@/components/layout/AppShell":{default:({children})=>React.createElement("main",null,children)},
        "@/lib/server-session":{requireSession:async()=>({role,sub:"alice"})},
        "@/lib/server-config":{serviceConfig:{deployment:"https://deployment.example",infrastructure:"https://infra.example"}},
        "@/lib/role-access":{selectAuthorizedProject},
        "@/lib/dashboard-api":{
          getAccessibleProjects:async()=>({data:[{id:"own",name:"My project"}]}),
          backendRequest:async()=>{calls++;return Response.json({items:[{id:"own-evidence",project_id:"own"},{id:"foreign-evidence",project_id:"foreign"}]});},
        },
        "./WorkspaceEvidence":{default:({items})=>React.createElement("pre",null,JSON.stringify(items))},
      });
      let html=renderToStaticMarkup(await Workspace({mode,requested:"foreign"}));
      assert.equal(calls,0);assert.match(html,/access denied/);assert.doesNotMatch(html,/foreign-evidence/);
      html=renderToStaticMarkup(await Workspace({mode,requested:"own"}));
      assert.equal(calls,1);assert.match(html,/own-evidence/);assert.doesNotMatch(html,/foreign-evidence/);
    }
  }
});

test("incident resolution preserves required API payload using the session actor", async (t) => {
  const {resolveIncident}=load("../src/lib/incidents-api.ts", {"@/lib/frontend-api":load("../src/lib/frontend-api.ts", {})});
  t.mock.method(globalThis,"fetch",async(_url,options)=>{
    const body=JSON.parse(options.body);
    assert.equal(body.resolved_by,"verified-session-actor");
    assert.equal(body.resolution_notes,"Evidence reviewed");
    return Response.json({status:"resolved"});
  });
  assert.equal((await resolveIncident("incident","Evidence reviewed","verified-session-actor")).status,"resolved");
});

test("project cost UI shows attributed history for every role and never substitutes account data", async () => {
  const React=require("react");const {renderToStaticMarkup}=require("react-dom/server");
  for (const role of ["developer","sre","platform-engineer"]) {
    let calls=0;
    const {default:Page}=load("../src/app/project-costs/page.tsx",{
      "@/components/layout/AppShell":{default:({children})=>React.createElement("main",null,children)},
      "@/components/finops/ProjectInsights":{default:({projectId})=>React.createElement("div",null,"Scoped insights: "+projectId)},
      "@/lib/role-access":{selectAuthorizedProject},
      "@/lib/server-session":{requireSession:async()=>({role,sub:"alice"})},
      "@/lib/server-config":{serviceConfig:{finops:"https://finops.example"}},
      "@/lib/dashboard-api":{getAccessibleProjects:async()=>({data:[{id:"own",name:"Own project"}]}),
        backendRequest:async(_session,_aud,url)=>{calls++;assert.ok(url.endsWith("/own/costs"));return Response.json({project_id:"own",status:"available",resources_with_cost:1,active_ec2_resources:2,costs:[{status:"estimated",currency:"USD",amount:"2.50"}],history:[{date:"2026-01-03",status:"estimated",currency:"USD",amount:"2.50"}]});}},
    });
    let html=renderToStaticMarkup(await Page({searchParams:Promise.resolve({project:"foreign"})}));
    assert.equal(calls,0);assert.match(html,/access was denied/);
    html=renderToStaticMarkup(await Page({searchParams:Promise.resolve({project:"own"})}));
    assert.equal(calls,1);assert.match(html,/2026-01-03/);assert.match(html,/estimated/);
    assert.match(html,/missing days are unavailable/);
    if(role==="developer")assert.doesNotMatch(html,/href="\/finops"/);
  }
});
