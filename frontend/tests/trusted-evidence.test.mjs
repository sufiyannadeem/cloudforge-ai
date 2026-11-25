import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import ts from "typescript";
const require=createRequire(import.meta.url);
const {outputText}=ts.transpileModule(readFileSync(new URL('../src/components/incidents/TrustedEvidencePanel.tsx',import.meta.url),'utf8'),{fileName:'TrustedEvidencePanel.tsx',compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
const exports={};Function('require','exports',outputText)((name)=>name==='@/lib/frontend-api'||name==='@/components/layout/ViewerSession'?{}:require(name),exports);
const View=exports.EvidenceOptionsView;
const item=(kind,advisory,effect)=>({kind,advisory_only:advisory,execution_supported:!advisory,effect,description:'<script>private</script>',evidence:['telemetry:cpu_pressure:123'],selection_source:'trusted_evidence'});
const data={project_id:'verified-project',signals:[{signal:'cpu_pressure',state:'unknown',reason:'stale'}],catalog:{diagnosis_status:'unavailable_or_stale',guidance:'Investigate or escalate.',items:[item('investigation',true,'inspect_cpu'),item('acknowledgement',false,'incident_acknowledgement'),item('infrastructure_remediation',true,'capacity_change')]}};
test('telemetry UI distinguishes investigation, workflow and advisory infrastructure',()=>{
 const html=renderToStaticMarkup(createElement(View,{data,onReject:()=>{}}));
 assert.match(html,/cpu_pressure: unknown \(stale\)/);assert.match(html,/Unknown telemetry is not healthy/);
 assert.match(html,/Investigation — read only/);assert.match(html,/Acknowledgement — workflow only/);
 assert.match(html,/Infrastructure remediation — advisory only/);assert.match(html,/independent Platform Engineer/);
 assert.match(html,/&lt;script&gt;private/);assert.doesNotMatch(html,/<script>|>Execute|>Apply|>Scale/);
});
test('missing safe options escalate instead of fabricating remediation',()=>{
 const html=renderToStaticMarkup(createElement(View,{data:{...data,catalog:{...data.catalog,items:[]}},onReject:()=>{}}));
 assert.match(html,/No safe evidence-supported option is available/);assert.match(html,/Investigate or escalate/);
});
test('advisory rejection submits only a normalized effect identifier',()=>{
 const calls=[];const tree=View({data,onReject:effect=>calls.push(effect)});
 function buttons(node){if(Array.isArray(node))return node.flatMap(buttons);if(!node||typeof node!=='object')return[];const children=node.props?.children;return[node.type==='button'?node:[],...(Array.isArray(children)?children:[children]).flatMap(buttons)].flat();}
 const all=buttons(tree);assert.equal(all.length,2);all[1].props.onClick();assert.deepEqual(calls,['capacity_change']);
});
test('local semantic status and runbook citations never imply execution authority',()=>{
 const html=renderToStaticMarkup(createElement(View,{data:{...data,knowledge:{retrieval_status:'pretrained-onnx',retrieval_backend:'pretrained-onnx'},catalog:{...data.catalog,items:[{...data.catalog.items[2],knowledge_citations:['knowledge:stable:content']}] }},onReject:()=>{}}));
 assert.match(html,/Local retrieval: pretrained-onnx/);assert.match(html,/Contextual runbook citations: knowledge:stable:content/);
 assert.match(html,/These do not prove live state/);assert.match(html,/advisory only/);assert.doesNotMatch(html,/>Execute|>Apply/);
});
