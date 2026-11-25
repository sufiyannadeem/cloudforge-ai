import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import ts from "typescript";
const require=createRequire(import.meta.url);
const source=readFileSync(new URL('../src/components/incidents/InferenceStatus.tsx',import.meta.url),'utf8');
const {outputText}=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
const exports={};Function('require','exports',outputText)(require,exports);
const Panel=exports.default;

test('blocked status never suggests successful inference or offers execution',()=>{
 const html=renderToStaticMarkup(createElement(Panel,{analysis:{status:'blocked',provider:'gemini',retrieval_status:'unavailable',citations:[]}}));
 assert.match(html,/AI status: blocked/);assert.match(html,/Retrieval: unavailable/);
 assert.match(html,/No AI conclusion is established/);assert.match(html,/No validated AI evidence citations/);
 assert.doesNotMatch(html,/<button|Execute|Approve|Apply|AI diagnosis succeeded/);
});
test('aggregate citations and contextual references remain distinct and escaped',()=>{
 const html=renderToStaticMarkup(createElement(Panel,{analysis:{status:'success',provider:'gemini',retrieval_status:'concept-v1',
  citations:['aggregate:latency:degraded'],knowledge_references:[{chunk_id:'latency:chunk-1',path:'runbooks/latency.md',title:'<script>private</script>'}]}}));
 assert.match(html,/aggregate:latency:degraded/);assert.match(html,/Citation: latency:chunk-1/);
 assert.match(html,/were not sent to the provider/);assert.match(html,/&lt;script&gt;/);
 assert.doesNotMatch(html,/<script>/);
});
test('old analyses expose truthful missing retrieval status',()=>{
 const html=renderToStaticMarkup(createElement(Panel,{analysis:{status:'deterministic',provider:'deterministic'}}));
 assert.match(html,/Retrieval: not requested/);
});
test('incident page opts into AI explicitly and retains deterministic actions',()=>{
 const page=readFileSync(new URL('../src/app/incidents/[id]/page.tsx',import.meta.url),'utf8');
 assert.match(page,/Request AI diagnosis/);
 assert.match(page,/await analyzeIncident\(incidentId\)/);
 assert.match(page,/await analyzeIncidentDeterministic\(/);
 assert.match(page,/<IncidentDetails key=\{params.id\}/);
 assert.match(page,/AI cannot approve or execute changes/);
});
test('AI and deterministic requests reuse CSRF protection and send no raw evidence',async(t)=>{
 function load(relative,aliases={}) {
  const input=readFileSync(new URL(relative,import.meta.url),'utf8');
  const {outputText}=ts.transpileModule(input,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
  const out={};Function('require','exports',outputText)((name)=>aliases[name]??require(name),out);return out;
 }
 const oldFetch=globalThis.fetch,oldDocument=globalThis.document;
 t.after(()=>{globalThis.fetch=oldFetch;if(oldDocument===undefined)delete globalThis.document;else globalThis.document=oldDocument;});
 globalThis.document={cookie:'cf_csrf=approved-csrf'};
 const calls=[];
 globalThis.fetch=async(url,options)=>{calls.push({url,options});return new Response(JSON.stringify({incident:{id:'owned'}}),{headers:{'content-type':'application/json'}});};
 const helper=load('../src/lib/frontend-api.ts');
 const api=load('../src/lib/incidents-api.ts',{'@/lib/frontend-api':helper});
 await api.analyzeIncident('owned');await api.analyzeIncidentDeterministic('owned');
 assert.equal(calls[0].url,'/api/proxy/aiops/api/v1/incidents/owned/analyze');
 assert.equal(calls[1].url,'/api/proxy/aiops/api/v1/incidents/owned/analyze/deterministic');
 for(const {options} of calls){assert.equal(options.method,'POST');assert.equal(options.headers['X-CSRF-Token'],'approved-csrf');assert.equal(options.body,undefined);assert.ok(options.signal);}
});
