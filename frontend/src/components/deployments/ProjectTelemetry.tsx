"use client";

import { useEffect, useState } from "react";
import ProjectDiagnosis from "./ProjectDiagnosis";

type Logs = { lines: string[]; next_page: number | null };
type Health = { desired_replicas: number | null; available_replicas: number | null; sampled_pod_restarts: number | null };
type Result<T> = { data: T } | { message: string };

async function read<T>(path: string, signal: AbortSignal): Promise<Result<T>> {
  try {
    const response = await fetch(path, { cache: "no-store", signal });
    if ([401, 403, 404].includes(response.status)) {
      return { message: "Deployment unavailable or access denied." };
    }
    if (response.ok) return { data: await response.json() };
  } catch {}
  return { message: "Verified telemetry is unavailable." };
}

export default function ProjectTelemetry({ id, close }: { id: string; close: () => void }) {
  const [page, setPage] = useState(0);
  const [logs, setLogs] = useState<{ page: number; result: Result<Logs> }>();
  const [health, setHealth] = useState<Result<Health>>();
  const base = `/api/proxy/deployment/api/v1/deployments/${encodeURIComponent(id)}`;

  useEffect(() => {
    const request = new AbortController();
    void read<Health>(`${base}/observability`, request.signal).then((result) => {
      if (!request.signal.aborted) setHealth(result);
    });
    return () => request.abort();
  }, [base]);

  useEffect(() => {
    const request = new AbortController();
    void read<Logs>(`${base}/logs?page=${page}`, request.signal).then((result) => {
      if (!request.signal.aborted) setLogs({ page, result });
    });
    return () => request.abort();
  }, [base, page]);

  const currentLogs = logs?.page === page ? logs.result : undefined;

  return (
    <section className="mt-6 space-y-4 rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Deployment logs and health</h2>
        <button type="button" onClick={close} className="text-sm underline">Close</button>
      </div>
      {!health ? <p role="status">Loading health…</p> : "message" in health ? <p role="status">{health.message}</p> :
        <dl className="grid gap-2 text-sm sm:grid-cols-3">
          <div><dt>Desired replicas</dt><dd>{health.data.desired_replicas ?? "Unavailable"}</dd></div>
          <div><dt>Available replicas</dt><dd>{health.data.available_replicas ?? "Unavailable"}</dd></div>
          <div><dt>Sampled pod restarts</dt><dd>{health.data.sampled_pod_restarts ?? "Unavailable"}</dd></div>
        </dl>}
      <ProjectDiagnosis id={id} />
      <h3 className="text-sm font-semibold">Recent application logs</h3>
      {!currentLogs ? <p role="status">Loading logs…</p> : "message" in currentLogs ? <p role="status">{currentLogs.message}</p> :
        currentLogs.data.lines.length > 0
          ? <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{currentLogs.data.lines.join("\n")}</pre>
          : <p role="status">No recent logs from verified pods on this page.</p>}
      <div className="flex gap-4 text-sm">
        {page > 0 && <button type="button" className="underline" onClick={() => setPage(page - 1)}>Previous pod</button>}
        {currentLogs && "data" in currentLogs && currentLogs.data.next_page === page + 1 &&
          <button type="button" className="underline" onClick={() => setPage(page + 1)}>Next pod</button>}
      </div>
    </section>
  );
}
