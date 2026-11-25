import type { AIAnalysis } from "@/types/incidents";

export default function InferenceStatus({ analysis }: { analysis: AIAnalysis }) {
  return <section aria-label="AI evidence and provider status" className="space-y-2 rounded border border-[var(--cf-border)] p-4">
    <p role="status">AI status: {analysis.status} · Provider: {analysis.provider} · Retrieval: {analysis.retrieval_status ?? "not requested"}</p>
    {analysis.status === "blocked" && <p>AI diagnosis is blocked or unavailable. No AI conclusion is established.</p>}
    {analysis.citations?.length ? <div><h3 className="font-semibold">Cited aggregate evidence</h3><ul>{analysis.citations.map((citation) => <li key={citation}>{citation}</li>)}</ul></div> : <p>No validated AI evidence citations.</p>}
    {!!analysis.knowledge_references?.length && <div><h3 className="font-semibold">Related documentation</h3>
      <p>Contextual references only; these do not establish causality and were not sent to the provider.</p>
      <ul>{analysis.knowledge_references.map((ref) => <li key={ref.chunk_id}>{ref.title} · {ref.path} · Citation: {ref.chunk_id}</li>)}</ul>
    </div>}
  </section>;
}
