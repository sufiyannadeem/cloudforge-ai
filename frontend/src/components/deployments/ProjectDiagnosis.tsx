"use client";

import { useEffect, useState } from "react";
import { frontendApi } from "@/lib/frontend-api";
import type { DiagnosticCapture } from "@/types/deployments";

const severities = { insufficient_data: "Insufficient evidence", info: "Informational", warning: "Warning", high: "High" };

export default function ProjectDiagnosis({ id }: { id: string }) {
  const [captures, setCaptures] = useState<DiagnosticCapture[]>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const request = new AbortController();
    void frontendApi.deployments.diagnostics(id, request.signal).then((history) => {
      if (!request.signal.aborted) setCaptures(history);
    }).catch(() => {
      if (request.signal.aborted) return;
      setError("Diagnostic history unavailable.");
      setCaptures([]);
    });
    return () => request.abort();
  }, [id]);

  async function capture() {
    setBusy(true);
    setError("");
    try {
      const result = await frontendApi.deployments.captureDiagnostic(id);
      setCaptures((previous) => [result, ...(previous ?? [])].slice(0, 10));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verified diagnostics unavailable.");
    } finally {
      setBusy(false);
    }
  }

  const latest = captures?.[0];
  const evidence = latest?.evidence;
  const sample = evidence?.sample;
  return (
    <section className="space-y-3 rounded-lg border border-[var(--cf-border)] p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">Kubernetes diagnosis</h3>
        <button type="button" disabled={!captures || busy} onClick={() => void capture()}
          className="rounded border border-[var(--cf-border)] px-3 py-2 disabled:opacity-50">
          {busy ? "Analyzing…" : "Analyze deployment"}
        </button>
      </div>
      {error && <p role="status">{error}</p>}
      {!captures && <p role="status">Loading diagnostic history…</p>}
      {captures && !latest && !error && <p>No saved samples for this deployment.</p>}
      {latest && evidence && <>
        <p className="text-xs text-[var(--cf-text-muted)]">Kubernetes evidence captured {new Date(evidence.observed_at).toLocaleString()} by {latest.actor}.</p>
        <p><strong>{severities[evidence.severity]}</strong> · {evidence.likely_cause}</p>
        <p>{evidence.recommendation} Changes require human approval.</p>
        <p>Rollout replicas available {evidence.available_replicas ?? "Unavailable"} / {evidence.desired_replicas ?? "Unavailable"}</p>
        {sample ? <dl className="space-y-2">
          <div><dt className="font-medium">Sampled pod</dt><dd>{sample.name} · {sample.phase || "Phase unavailable"} · {sample.restarts ?? "Unavailable"} restarts</dd></div>
          <div><dt className="font-medium">Status and events</dt><dd>{sample.reasons.join(", ") || "No supported warning observed"}{sample.events_checked ? "" : " · Events unavailable"}</dd></div>
          <div><dt className="font-medium">Log signal</dt><dd>{sample.logs_checked ? sample.log_error_signal ? "Fatal or panic marker found" : "No fatal or panic marker in the sampled lines" : "Unavailable"}</dd></div>
          <div><dt className="font-medium">Container usage</dt><dd>{sample.usage ? `CPU ${sample.usage.cpu} · memory ${sample.usage.memory}` : "Unavailable"}</dd></div>
        </dl> : <p>No verified pod sample was available.</p>}
      </>}
      {captures && captures.length > 1 && <details>
        <summary className="cursor-pointer">Previous captures</summary>
        <ul className="mt-2 space-y-1">
          {captures.slice(1).map((item) => <li key={item.id}>
            {new Date(item.captured_at).toLocaleString()} · {item.actor} · {severities[item.evidence.severity]} · {item.evidence.likely_cause}
          </li>)}
        </ul>
      </details>}
    </section>
  );
}
