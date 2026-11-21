"use client";
import { useEffect, useState } from "react";

type Evidence = {
  status: string; project_id?: string; resource_id?: string; basis?: string; reason?: string;
  evidence?: { costs: { status: string; currency: string; amount: string }[] };
};
export default function IncidentCostEvidence({ incidentId }: { incidentId: string }) {
  const [data, setData] = useState<Evidence | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/incidents/${encodeURIComponent(incidentId)}/cost-evidence`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error("unavailable"); return response.json(); })
      .then(setData).catch(() => { if (!controller.signal.aborted) setData({ status: "unavailable" }); });
    return () => controller.abort();
  }, [incidentId]);
  return <section className="space-y-2 rounded-xl border border-[var(--cf-border)] p-4">
    <h2 className="text-lg font-semibold">Resource cost evidence</h2>
    {!data ? <p role="status">Loading cost evidence…</p> : data.status !== "available" ?
      <p>{data.reason ?? "Verified resource cost evidence unavailable."}</p> : <>
      <p>Project {data.project_id} · Resource {data.resource_id}</p>
      <p>{data.basis}</p>
      {data.evidence?.costs.map((cost, index) => <p key={index}>{cost.status} · {cost.currency} {cost.amount}</p>)}
    </>}
  </section>;
}
