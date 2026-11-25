"use client";
import {useState} from "react";
import {frontendApiRequest} from "@/lib/frontend-api";
import {useViewerSession} from "@/components/layout/ViewerSession";

export type EvidenceOption = {effect:string;kind:"investigation"|"acknowledgement"|"infrastructure_remediation";description:string;advisory_only:boolean;execution_supported:boolean;requires_pe_approval:boolean;evidence:string[];selection_source:string;knowledge_citations?:string[]};
export type TrustedOptions = {incident_id:string;project_id:string;provenance:string;knowledge?:{retrieval_status:string;retrieval_backend:string};signals:{signal:string;state:string;reason:string|null;observed_at:number|null}[];catalog:{diagnosis_status:string;items:EvidenceOption[];guidance:string}};

export function EvidenceOptionsView({data,onReject,busy=false}:{data:TrustedOptions;onReject:(effect:string)=>void;busy?:boolean}) {
 return <div className="space-y-3">
  <p>Authoritative project scope: {data.project_id} · AI context: {data.catalog.diagnosis_status}</p>
  <p>Local retrieval: {data.knowledge?.retrieval_status ?? "not requested"} · Backend: {data.knowledge?.retrieval_backend ?? "unavailable"}</p>
  <p>Unknown telemetry is not healthy. Rich signals stay internal; loading this panel does not call AI.</p>
  <ul>{data.signals.map(signal=><li key={signal.signal}>{signal.signal}: {signal.state}{signal.reason ? ` (${signal.reason})` : ""}</li>)}</ul>
  {data.catalog.items.map(item=><article key={item.effect} className="rounded border border-[var(--cf-border)] p-3">
   <h4>{item.kind==="investigation" ? "Investigation — read only" : item.kind==="acknowledgement" ? "Acknowledgement — workflow only" : item.advisory_only ? "Infrastructure remediation — advisory only" : "Infrastructure remediation — separate approval required"}</h4>
   <p>{item.description}</p><p className="text-xs">Evidence: {item.evidence.join(", ")} · {item.selection_source}</p>
   {!!item.knowledge_citations?.length && <p>Contextual runbook citations: {item.knowledge_citations.join(", ")}. These do not prove live state.</p>}
   {item.advisory_only ? <><p>No execution is requested or available from this advisory.</p><button type="button" disabled={busy} onClick={()=>onReject(item.effect)} className="rounded border p-2">Reject advisory effect</button></> : <p>Use the existing proposal review below. Fresh independent Platform Engineer approval is required before any change.</p>}
  </article>)}
  {data.catalog.items.length===0 && <p>No safe evidence-supported option is available. Investigate or escalate.</p>}
  <p>{data.catalog.guidance}</p>
 </div>;
}

export default function TrustedEvidencePanel({incidentId}:{incidentId:string}) {
 const viewer=useViewerSession();
 const [data,setData]=useState<TrustedOptions|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [reason,setReason]=useState("");
 const base=`/api/proxy/aiops/api/v1/incidents/${encodeURIComponent(incidentId)}/remediation`;
 async function load() {
  setBusy(true);setError("");
  try {
   const value=await frontendApiRequest<TrustedOptions>(`${base}/evidence`,{signal:AbortSignal.timeout(8000)});
   if(value.incident_id!==incidentId || value.provenance!=="verified_resource_v1" || !Array.isArray(value.signals) || !Array.isArray(value.catalog?.items)) throw new Error("Evidence scope or provenance mismatch");
   setData(value);
  } catch(err) {setData(null);setError(err instanceof Error?err.message:"Evidence unavailable");}
  finally {setBusy(false);}
 }
 async function reject(effect:string) {
  setBusy(true);setError("");
  try {
   await frontendApiRequest(`${base}/advisories/${encodeURIComponent(effect)}/reject`,{method:"POST",body:JSON.stringify({rejected_by:viewer?.username,reason:reason.trim()||undefined}),signal:AbortSignal.timeout(8000)});
   setReason("");await load();
  } catch(err) {setError(err instanceof Error?err.message:"Advisory rejection unavailable");}
  finally {setBusy(false);}
 }
 return <section aria-label="Trusted telemetry and safe options" className="space-y-3 rounded border border-[var(--cf-border)] p-4">
  <h3 className="font-semibold">Trusted telemetry and evidence-based options</h3>
  <button type="button" onClick={()=>void load()} disabled={busy||!viewer} className="rounded border p-2">Load trusted evidence and options</button>
  {error && <p role="status">{error}</p>}
  {data && <><label>Optional internal advisory rejection reason<textarea value={reason} maxLength={2000} onChange={event=>setReason(event.target.value)} className="block w-full rounded border p-2" /></label>
   <p>Advisory rejection suppresses future suggestions for this effect; it does not cancel an already dispatched action. Reasons remain internal.</p>
   <EvidenceOptionsView data={data} onReject={effect=>void reject(effect)} busy={busy||!viewer}/></>}
 </section>;
}
