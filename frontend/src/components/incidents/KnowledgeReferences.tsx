"use client";
import { useEffect, useState } from "react";
import { frontendApiRequest } from "@/lib/frontend-api";

type References = { retrieval_status?: string; retrieval_backend?: string; incident_id: string; authoritative: false; references: {
  path: string; title: string; chunk_id: string; matched_terms: string[];
}[] };

export default function KnowledgeReferences({ incidentId }: { incidentId: string }) {
  return <KnowledgeQuery key={incidentId} incidentId={incidentId} />;
}

function KnowledgeQuery({ incidentId }: { incidentId: string }) {
  const [result, setResult] = useState<References | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void frontendApiRequest<References>(`/api/proxy/aiops/api/v1/incidents/${encodeURIComponent(incidentId)}/knowledge`, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (data.incident_id !== incidentId || data.authoritative !== false || !Array.isArray(data.references)) throw new Error("Mismatched references");
        setResult(data);
      }).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [incidentId]);
  return <section className="space-y-2 rounded border border-[var(--cf-border)] p-4">
    <h2 className="font-semibold">RAG references</h2>
    <p className="text-sm">Local documentation retrieval. Context only; these references do not prove live state or root cause. No external inference is requested. A configured pretrained backend embeds queries locally.</p>
    {result && <p role="status">Retrieval: {result.retrieval_status ?? "unknown"} · Backend: {result.retrieval_backend ?? "unavailable"}</p>}
    {error ? <p role="status">Knowledge references unavailable or project access denied.</p> : !result ? <p role="status">Loading references…</p> : result.retrieval_status === "unavailable" ? <p>Documentation retrieval is unavailable.</p> : result.references.length === 0 ? <p>No matching operational documentation.</p> :
      <ul>{result.references.map((ref) => <li key={ref.chunk_id}><strong>{ref.title}</strong> · {ref.path} · Citation: {ref.chunk_id}</li>)}</ul>}
  </section>;
}
