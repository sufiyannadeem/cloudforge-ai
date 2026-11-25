"use client";
import Link from "next/link";
import { useState } from "react";
import type { CloudForgeRole } from "@/lib/auth";
import type { Deployment, InfrastructureResource } from "@/types/api";
import ProjectTelemetry from "@/components/deployments/ProjectTelemetry";
import DriftHistory from "@/components/infrastructure/DriftHistory";

export default function WorkspaceEvidence({ mode, items, role }: {
  mode: "agent" | "drift"; items: (Deployment | InfrastructureResource)[]; role: CloudForgeRole;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  return <div className="space-y-4">{items.map((item) => <article key={item.id} className="space-y-3 rounded border border-[var(--cf-border)] p-4">
    <h2 className="font-semibold">{"name" in item ? item.name : `${item.environment} · ${item.image}`}</h2>
    <p className="text-sm">{item.status} · {item.id}</p>
    {mode === "agent" ? <>
      <button className="underline" type="button" onClick={() => setSelected(item.id)}>Inspect logs, metrics and diagnosis</button>
      {selected === item.id && <ProjectTelemetry key={item.id} id={item.id} close={() => setSelected(null)} />}
    </> : <>
      <DriftHistory resourceId={item.id} scanAllowed={role !== "developer" && item.status === "active"} />
      <Link className="text-sm underline" href={`/infrastructure?resource=${encodeURIComponent(item.id)}`}>Review configuration and remediation approval history</Link>
    </>}
  </article>)}</div>;
}
