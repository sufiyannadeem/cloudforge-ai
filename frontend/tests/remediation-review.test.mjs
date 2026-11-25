import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import ts from "typescript";
const require=createRequire(import.meta.url);
function load(path,aliases={}) {
 const {outputText}=ts.transpileModule(readFileSync(new URL(path,import.meta.url),'utf8'),{fileName:path,compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
 const exports={};Function('require','exports',outputText)((name)=>Object.hasOwn(aliases,name)?aliases[name]:require(name),exports);return exports;
}
const permissions=load('../src/lib/remediation-review.ts');
const pending={id:'p1',incident_id:'owned',recommendation_version:2,project_id:'project',resource_scope:'resource',action_fingerprint:'a'.repeat(64),alternative_of:'p0',
 action:'acknowledge_incident',status:'PENDING_APPROVAL',policy_decision:'requires_approval',policy_reason:'Workflow only',proposed_by:'alice',approved_by:null,approved_role:null,
 parameters:{},created_at:new Date().toISOString(),expires_at:new Date(Date.now()+60_000).toISOString()};

test('only independent Platform Engineers can approve a fresh exact version',()=>{
 assert.equal(permissions.canApproveRecommendation(pending,{username:'bob',role:'platform-engineer'}),true);
 for(const user of [null,{username:'alice',role:'platform-engineer'},{username:'bob',role:'sre'},{username:'bob',role:'developer'}])assert.equal(Boolean(permissions.canApproveRecommendation(pending,user)),false);
 assert.equal(permissions.canApproveRecommendation({...pending,state_snapshot:{target:{created_by:'bob'}}},{username:'bob',role:'platform-engineer'}),false);
 for(const override of [{recommendation_version:0},{action_fingerprint:null},{expires_at:'2000-01-01'},{status:'REJECTED'}])assert.equal(permissions.canApproveRecommendation({...pending,...override},{username:'bob',role:'platform-engineer'}),false);
});
test('SRE reviewers may reject; they cannot execute approved mutations',()=>{
 assert.equal(permissions.canRejectRecommendation(pending,{username:'sre',role:'sre'}),true);
 const approved={...pending,status:'APPROVED',approved_by:'bob',approved_role:'platform-engineer'};
 assert.equal(permissions.canExecuteRecommendation(approved,{username:'carol',role:'platform-engineer'}),true);
 assert.equal(permissions.canExecuteRecommendation(approved,{username:'sre',role:'sre'}),false);
 assert.equal(permissions.canExecuteRecommendation({...approved,approved_by:'alice'},{username:'carol',role:'platform-engineer'}),false);
});
function panel(proposals,viewer,history=null) {
 const states=[history,'',{incident_id:'owned',proposals,available_actions:[]},'acknowledge_incident','','',{},false,false,''];
 return load('../src/components/incidents/RemediationPanel.tsx',{
  react:{useState:()=>[states.shift(),()=>{}],useRef:()=>({current:{}}),useEffect:()=>{},useMemo:f=>f(),useCallback:f=>f},
  '@/components/incidents/TrustedEvidencePanel':{default:()=>null},'@/components/layout/ViewerSession':{useViewerSession:()=>viewer},'@/lib/incidents-api':{},'@/lib/remediation-review':permissions,
 }).default;
}
test('review controls expose version/scope and optional internal rejection',()=>{
 const Panel=panel([pending],{username:'alice',role:'platform-engineer'});
 const html=renderToStaticMarkup(createElement(Panel,{incidentId:'owned'}));
 assert.match(html,/Version 2/);assert.match(html,/Scope project \/ resource/);assert.match(html,/Alternative to p0/);
 assert.match(html,/Optional internal rejection reason. Never sent to AI/);
 assert.match(html,/disabled=""[^>]*>Approve remediation/);assert.match(html,/Load internal review history/);
});
test('rejected recommendations offer alternatives without auto execution and escape reasons',()=>{
 const Panel=panel([{...pending,status:'REJECTED'}],{username:'bob',role:'sre'},[{id:1,event_type:'rejected',recommendation_version:2,actor:'bob',created_at:pending.created_at,reason:'<script>private</script>'}]);
 const html=renderToStaticMarkup(createElement(Panel,{incidentId:'owned'}));
 assert.match(html,/Request safe alternative or investigation/);assert.match(html,/Internal recommendation history/);
 assert.match(html,/&lt;script&gt;private/);assert.doesNotMatch(html,/Execute remediation|<script>/);
});
test('API carries exact review version and an explicit idempotency key',async()=>{
 const calls=[];const api=load('../src/lib/incidents-api.ts',{'@/lib/frontend-api':{frontendApiRequest:async(url,options)=>{calls.push({url,options});return{};}}});
 await api.approveIncidentRemediation('owned','p1','bob',2,pending.action_fingerprint);
 await api.rejectIncidentRemediation('owned','p1','bob');await api.requestRemediationAlternative('owned','p1');
 await api.executeIncidentRemediation('owned','p1','bob','stable-idempotency-key');
 assert.deepEqual(JSON.parse(calls[0].options.body),{approved_by:'bob',expected_version:2,expected_fingerprint:pending.action_fingerprint});
 assert.deepEqual(JSON.parse(calls[1].options.body),{rejected_by:'bob'});assert.equal(calls[2].options.body,undefined);
 assert.equal(JSON.parse(calls[3].options.body).idempotency_key,'stable-idempotency-key');
});
