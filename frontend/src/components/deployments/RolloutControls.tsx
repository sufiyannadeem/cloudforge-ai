"use client";

import { useState } from "react";
import type { Deployment } from "@/types/deployments";

interface State {
  uid: string; resource_version: string; phase: string;
  preview_service: string; preview_ready: boolean;
  promotion_required: boolean; traffic_mode: string;
}
interface Audit { id: string; actor: string; outcome: string; approved_at: string; }

export default function RolloutControls({ deployment, operator, csrfHeaders }: {
  deployment: Deployment; operator: boolean; csrfHeaders: () => Record<string, string>;
}) {
  const [state, setState] = useState<State | null>(null);
  const [history, setHistory] = useState<Audit[]>([]);
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const base = `/api/proxy/deployment/api/v1/deployments/${deployment.id}`;

  async function preview() {
    setBusy(true); setApproved(false); setMessage(""); setState(null);
    try {
      const response = await fetch(`${base}/rollout`, { cache: "no-store" });
      if (!response.ok) throw new Error("Verified rollout state unavailable. Check Argo prerequisites, baseline and project access.");
      const data = await response.json();
      setState(data.state); setHistory(data.history ?? []);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to read rollout"); }
    finally { setBusy(false); }
  }
  async function promote() {
    if (!state || !approved) return;
    setBusy(true); setApproved(false); setMessage("");
    try {
      const response = await fetch(`${base}/promote`, {
        method: "POST", headers: { "Content-Type": "application/json", ...csrfHeaders() },
        body: JSON.stringify({ uid: state.uid, resource_version: state.resource_version, approve: true }),
      });
      if (!response.ok) throw new Error("Promotion denied or uncertain. An independent Platform Engineer must approve a ready, unchanged preview. Reload and inspect audit history; do not retry an uncertain action.");
      setMessage("Promotion submitted. Argo health determines completion; refresh deployment history.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Promotion unavailable"); }
    finally { setBusy(false); setState(null); }
  }
  return <div className="space-y-2 rounded-lg border border-[var(--cf-border)] p-3 text-sm">
    <button type="button" className="rounded-lg border border-[var(--cf-border)] px-3 py-2 font-semibold disabled:opacity-50" disabled={busy} onClick={() => void preview()}>
      {busy ? "Checking rollout…" : "Preview rollout and approval history"}
    </button>
    {message && <p role="status">{message}</p>}
    {state && <>
      <p>{state.phase} · {state.traffic_mode}</p>
      <p>Revision pods: {state.preview_ready ? "Ready" : "Not ready / insufficient evidence"}</p>
      {state.preview_service && <p>Preview Service: <code>{state.preview_service}</code> (project namespace only)</p>}
      {operator && deployment.status === "running" && state.phase === "Paused" && state.promotion_required && state.preview_ready && <>
        <label className="flex items-center gap-2 break-all"><input type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} />
          I approve activation of this exact image: {deployment.image}
        </label>
        <button type="button" className="rounded-lg bg-indigo-600 px-3 py-2 font-semibold text-white hover:bg-indigo-500 disabled:opacity-50" disabled={busy || !approved} onClick={() => void promote()}>Approve and promote preview</button>
        <p>The requester cannot self-approve. Approval is single-use and bound to this observed revision.</p>
      </>}
    </>}
    {history.length > 0 && <ul aria-label="Promotion audit history">{history.map((item) => <li key={item.id}>{item.actor} · {item.outcome} · {new Date(item.approved_at).toLocaleString()}</li>)}</ul>}
  </div>;
}
