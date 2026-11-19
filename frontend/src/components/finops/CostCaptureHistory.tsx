"use client";

import { useState } from "react";
import { captureCostAnomalies, listCostAnomalyCaptures } from "@/lib/finops-api";
import type { CostAnomalyCapture } from "@/types/finops";

export default function CostCaptureHistory() {
  const [history, setHistory] = useState<CostAnomalyCapture[]>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function load(save: boolean) {
    setBusy(true);
    setMessage("");
    try {
      if (save) {
        await captureCostAnomalies();
        setMessage("Cost evidence saved.");
      }
      setHistory(await listCostAnomalyCaptures());
    } catch {
      setMessage("Cost audit storage or AWS evidence is unavailable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="mt-4 rounded-lg border border-[var(--cf-border)] p-3 text-sm" onToggle={(event) => {
      if (event.currentTarget.open && !history && !busy) void load(false);
    }}>
      <summary className="cursor-pointer font-semibold">Cost evidence history</summary>
      <button type="button" disabled={busy} onClick={() => void load(true)}
        className="my-2 rounded border border-[var(--cf-border)] px-3 py-2 disabled:opacity-50">
        {busy ? "Loading…" : "Capture current evidence"}
      </button>
      {message && <p role="status">{message}</p>}
      {history?.length === 0 && !message && <p>No saved cost evidence for this AWS account.</p>}
      {history && history.length > 0 && <ul className="space-y-1">
        {history.map((item) => <li key={item.id}>
          {new Date(item.captured_at).toLocaleString()} · {item.actor} · {item.evidence.sample_count} samples ·{" "}
          {item.evidence.sufficient_data ? `${item.evidence.anomalies.length} anomalies` : "insufficient data"}
        </li>)}
      </ul>}
    </details>
  );
}
