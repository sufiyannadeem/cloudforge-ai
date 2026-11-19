"use client";
import { useCallback, useEffect, useState } from "react";
import type { ReliabilityRow } from "@/lib/platform-reliability";

export default function PlatformReliability() {
  const [rows, setRows] = useState<ReliabilityRow[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/platform-reliability", { cache: "no-store" });
      if (!response.ok) throw new Error(response.status === 403 ? "Operator access required" : "Scaling evidence unavailable");
      const data = await response.json(); setRows(data.rows);
    } catch (error) { setRows(null); setError(error instanceof Error ? error.message : "Scaling evidence unavailable"); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { const timer = setTimeout(() => void load(), 0); const interval = setInterval(() => void load(), 30000); return () => { clearTimeout(timer); clearInterval(interval); }; }, [load]);
  const measured = (value: number | null) => value === null ? "N/A" : value;
  return <section className="space-y-3 rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-xl font-semibold">Platform scaling and readiness</h2>
      <button type="button" disabled={busy} className="rounded border px-3 py-1 disabled:opacity-50" onClick={() => void load()}>{busy ? "Loading…" : "Refresh scaling evidence"}</button></div>
    <p className="text-xs text-[var(--cf-text-muted)]">Kubernetes replica counts in the platform namespace. N/A means missing, stale or unavailable evidence; it does not mean healthy. Requires kube-state-metrics.</p>
    {error && <p role="alert">{error}</p>}
    {rows && <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th>Service</th><th>Available / desired</th><th>HPA current / desired</th><th>Scaling capped</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.service}><td className="py-2">{row.service}</td><td>{measured(row.available)} / {measured(row.desired)}</td><td>{measured(row.hpaCurrent)} / {measured(row.hpaDesired)}</td><td>{row.scalingLimited === null ? "N/A" : row.scalingLimited === 1 ? "Yes" : "No"}</td></tr>)}</tbody></table></div>}
  </section>;
}
