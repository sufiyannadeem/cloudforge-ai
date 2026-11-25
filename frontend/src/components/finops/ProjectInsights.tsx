"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { frontendApiRequest } from "@/lib/frontend-api";

type Quality = "actual" | "estimated" | "unavailable";
type Resource = {
  resource_id: string; status: "available" | "partial" | "unavailable"; billing_quality: Quality;
  reason?: string; sample_count?: number; telemetry_quality?: Quality; cpu_utilization_percent?: number;
  anomalies?: { date: string; amount: number; currency: string; severity: string; evidence_quality: Quality; reason: string }[];
  recommendations?: { resource_id: string; reason: string; recommendation: string; action: string;
    potential_monthly_savings_usd: number | null; savings: { evidence_available: boolean; monthly_usd: number | null; calculation: string } }[];
};
export type ProjectInsight = {
  project_id: string; status: "available" | "partial" | "unavailable"; advisory_only: true;
  resources: Resource[]; observed_at?: string;
};

export function validateProjectInsight(data: ProjectInsight, projectId: string): ProjectInsight {
  if (data.project_id !== projectId || data.advisory_only !== true || !Array.isArray(data.resources)) {
    throw new Error("Project insight evidence unavailable or scope mismatch.");
  }
  if (data.resources.some((resource) => resource.recommendations?.some((finding) => finding.resource_id !== resource.resource_id))) {
    throw new Error("Recommendation resource mismatch.");
  }
  return data;
}

export default function ProjectInsights({ projectId }: { projectId: string }) {
  const [results, setResults] = useState<Partial<Record<"anomalies" | "optimizations", ProjectInsight>>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), [projectId]);
  async function load(kind: "anomalies" | "optimizations") {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    setBusy(true); setError("");
    // Do not keep an older result looking current after a failed refresh.
    setResults((previous) => ({ ...previous, [kind]: undefined }));
    try {
      const data = await frontendApiRequest<ProjectInsight>(`/api/proxy/finops/api/v1/finops/projects/${encodeURIComponent(projectId)}/${kind}`, { signal: controller.signal });
      const checked = validateProjectInsight(data, projectId);
      if (!controller.signal.aborted) setResults((previous) => ({ ...previous, [kind]: checked }));
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Project insights unavailable.");
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section className="space-y-4 rounded-lg border border-[var(--cf-border)] p-4" aria-label="Project cost insights">
    <h2 className="font-semibold">Project anomalies and optimization</h2>
    <p className="text-sm">Read-only analysis of verified project EC2 resources. Missing data is unavailable. Recommendations are advisory and require independent review; this page cannot change AWS resources.</p>
    <div className="flex gap-3"><button type="button" disabled={busy} className="rounded border px-3 py-2 disabled:opacity-50" onClick={() => void load("anomalies")}>Analyze project anomalies</button>
      <button type="button" disabled={busy} className="rounded border px-3 py-2 disabled:opacity-50" onClick={() => void load("optimizations")}>Review project optimization</button></div>
    {busy && <p role="status">Loading verified project evidence…</p>}
    {error && <p role="alert">{error}</p>}
    {(["anomalies", "optimizations"] as const).map((kind) => {
      const data = results[kind]?.project_id === projectId ? results[kind] : undefined;
      return data && <section key={kind} className="space-y-3" aria-label={kind}>
        <h3 className="font-semibold">{kind === "anomalies" ? "Cost anomalies · 14-day window" : "Optimization · 24-hour utilization window"} · {data.status}</h3>
        {data.observed_at && <p className="text-xs">Evidence read at {new Date(data.observed_at).toLocaleString()}. Refresh to revalidate.</p>}
        {data.resources.length === 0 && <p>No verified project resource evidence is available.</p>}
        {data.resources.map((resource) => <article key={resource.resource_id} className="space-y-2 rounded border p-3 text-sm">
          <h4 className="break-all font-medium">Resource {resource.resource_id}</h4>
          <p>Analysis: {resource.status} · Billing: {resource.billing_quality}</p>
          {resource.reason && <p>{resource.reason}</p>}
          {kind === "anomalies" ? <>
            <p>Attributed billing samples: {resource.sample_count ?? "Unavailable"}</p>
            {resource.status === "available" && resource.anomalies?.length === 0 && <p>No anomalies detected in the sufficient observed series.</p>}
            {resource.anomalies?.map((finding) => <p key={`${finding.date}-${finding.currency}`}>{finding.date} · {finding.amount} {finding.currency} · {finding.severity} · {finding.evidence_quality}. {finding.reason}</p>)}
          </> : <>
            <p>CPU utilization: {resource.telemetry_quality === "actual" ? `${resource.cpu_utilization_percent}% (observed)` : "Unavailable"}</p>
            {resource.status === "available" && resource.recommendations?.length === 0 && <p>No CPU-based optimization finding; this is not a memory or peak-capacity assessment.</p>}
            {resource.recommendations?.map((finding, index) => <div key={index} className="space-y-1">
              <p>{finding.reason} {finding.recommendation}</p>
              <p>Monthly savings: {finding.savings.evidence_available && finding.potential_monthly_savings_usd !== null ? `${finding.potential_monthly_savings_usd} USD (estimated)` : "Unavailable; no savings inferred."}</p>
              <p>{finding.savings.calculation} · {finding.action}</p>
              <Link className="underline" href={`/infrastructure?resource=${encodeURIComponent(resource.resource_id)}`}>Review request and independent approval history</Link>
            </div>)}
          </>}
        </article>)}
      </section>;
    })}
  </section>;
}
