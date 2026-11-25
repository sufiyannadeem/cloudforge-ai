"use client";

import Link from "next/link";
import { useState } from "react";

import { frontendApi } from "@/lib/frontend-api";
import type { TerraformDriftScan } from "@/types/infrastructure";

export default function DriftHistory({ resourceId, scanAllowed, onPlan }: {
  resourceId: string;
  scanAllowed: boolean;
  onPlan?: () => void;
}) {
  const [history, setHistory] = useState<TerraformDriftScan[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function request(capture = false) {
    setBusy(true);
    setError("");
    try {
      if (capture) {
        const scan = await frontendApi.infrastructure.scanDrift(resourceId);
        setHistory((current) => [scan, ...(current ?? [])].slice(0, 10));
      } else {
        setHistory(await frontendApi.infrastructure.driftHistory(resourceId));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Drift history unavailable.");
    } finally {
      setBusy(false);
    }
  }

  const latest = history?.[0];
  return (
    <section className="mt-2 space-y-2 text-sm" aria-label="Terraform drift">
      <div className="flex flex-wrap gap-3">
        <button type="button" disabled={busy} onClick={() => void request()} className="underline">Drift history</button>
        {scanAllowed && <button type="button" disabled={busy} onClick={() => void request(true)} className="underline">Scan for drift</button>}
      </div>
      {busy && <p role="status">Reading Terraform drift evidence…</p>}
      {error && <p role="alert">{error}</p>}
      {history?.length === 0 && <p>No drift scans recorded.</p>}
      {latest?.findings?.some(({ severity }) => severity === "high") && <p role="alert">Latest scan found high-severity changes.</p>}
      {latest?.findings?.length ? (
        <div className="flex flex-wrap gap-3">
          {onPlan && <button type="button" onClick={onPlan} className="underline">Generate plan for approval</button>}
          {scanAllowed && <><Link href="/incidents" className="underline">Review incidents</Link> <Link href="/finops" className="underline">Review AWS costs</Link></>}
        </div>
      ) : null}
      {history?.map((scan) => (
        <details key={scan.id}>
          <summary>{new Date(scan.scanned_at).toLocaleString()} · {scan.status === "unavailable" ? "Evidence unavailable" : scan.findings?.length ? `${scan.findings.length} findings` : "No changes observed"}</summary>
          {scan.findings?.map((finding, index) => (
            <div key={index}><p>{finding.address ?? finding.type} · {finding.source === "provider_drift" ? "Provider drift" : "Desired configuration change"} · {finding.severity}. {finding.risk} {finding.recommendation}</p>
            {finding.comparisons?.length ? <table className="my-2 w-full text-left"><caption>Safe configuration comparison</caption><thead><tr><th>Field</th><th>{finding.source === "provider_drift" ? "Recorded" : "Observed"}</th><th>{finding.source === "provider_drift" ? "Observed" : "Desired"}</th></tr></thead><tbody>{finding.comparisons.map((change) => <tr key={change.field}><td>{change.field}</td><td>{String(change.before)}</td><td>{String(change.after)}</td></tr>)}</tbody></table> : <p className="text-xs">Attribute comparison unavailable or withheld. Raw state and sensitive values are never displayed.</p>}</div>
          ))}
        </details>
      ))}
    </section>
  );
}
