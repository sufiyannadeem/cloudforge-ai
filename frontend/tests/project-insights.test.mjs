import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
const require=createRequire(import.meta.url);
function load(aliases={}) {
  const {outputText}=ts.transpileModule(readFileSync(new URL("../src/components/finops/ProjectInsights.tsx",import.meta.url),"utf8"),{
    compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
  const exports={};
  Function("require","exports",outputText)((name)=>Object.hasOwn(aliases,name)?aliases[name]:require(name),exports);
  return exports;
}
const evidence={project_id:"own",status:"partial",advisory_only:true,resources:[{
  resource_id:"resource",status:"available",billing_quality:"estimated",telemetry_quality:"actual",cpu_utilization_percent:5,
  recommendations:[{resource_id:"resource",reason:"Low measured CPU",recommendation:"Review memory and peaks",action:"HUMAN_APPROVAL_REQUIRED",potential_monthly_savings_usd:null,savings:{monthly_usd:null,evidence_available:false,calculation:"Target pricing unavailable"}}],
}]};
const link={default:({children,href})=>createElement("a",{href},children)};

test("insights reject foreign projects and resource-mismatched findings",()=>{
  const {validateProjectInsight}=load({"next/link":link,"@/lib/frontend-api":{}});
  assert.equal(validateProjectInsight(evidence,"own"),evidence);
  assert.throws(()=>validateProjectInsight(evidence,"foreign"),/scope mismatch/);
  assert.throws(()=>validateProjectInsight({...evidence,advisory_only:false},"own"));
  const wrong=structuredClone(evidence);wrong.resources[0].recommendations[0].resource_id="foreign";
  assert.throws(()=>validateProjectInsight(wrong,"own"),/resource mismatch/);
});

test("rendering labels estimates and unavailable savings without offering an apply action",()=>{
  const states=[{optimizations:evidence},false,""];
  const {default:Panel}=load({react:{useState:()=>[states.shift(),()=>{}],useRef:()=>({current:null}),useEffect:()=>{}},"next/link":link,"@/lib/frontend-api":{}});
  const html=renderToStaticMarkup(createElement(Panel,{projectId:"own"}));
  assert.match(html,/Billing: estimated/);assert.match(html,/Unavailable; no savings inferred/);
  assert.match(html,/HUMAN_APPROVAL_REQUIRED/);assert.match(html,/independent approval history/);
  assert.doesNotMatch(html,/0 USD|Execute|Apply optimization/);
});

test("buttons request only scoped GET APIs and failed refresh removes old evidence",async()=>{
  const state=[{optimizations:evidence},false,""];let cursor=0;const calls=[];
  const hooks={useState:(initial)=>{const i=cursor++;if(state[i]===undefined)state[i]=initial;return[state[i],value=>{state[i]=typeof value==="function"?value(state[i]):value;}];},useRef:()=>({current:null}),useEffect:()=>{}};
  let fail=false;
  const api={frontendApiRequest:async(path,options)=>{calls.push({path,options});if(fail)throw new Error("Evidence unavailable");return evidence;}};
  const {default:Panel}=load({react:hooks,"next/link":link,"@/lib/frontend-api":api});
  function tree(){cursor=0;return Panel({projectId:"own"});}
  function buttons(node){if(!node||typeof node!=="object")return[];const children=node.props?.children;return[node.type==="button"?node:[],...(Array.isArray(children)?children:[children]).flatMap(buttons)].flat();}
  // No inference, account inventory or automatic analysis during render.
  let roots=buttons(tree());assert.equal(calls.length,0);
  roots[1].props.onClick();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(calls[0].path,"/api/proxy/finops/api/v1/finops/projects/own/optimizations");
  assert.equal(calls[0].options.method,undefined);assert.equal(state[0].optimizations,evidence);
  fail=true;roots=buttons(tree());roots[1].props.onClick();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(state[0].optimizations,undefined);assert.equal(state[2],"Evidence unavailable");
  fail=false;roots=buttons(tree());roots[0].props.onClick();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(calls[2].path,"/api/proxy/finops/api/v1/finops/projects/own/anomalies");
});
