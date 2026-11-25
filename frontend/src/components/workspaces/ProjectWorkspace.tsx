import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { backendRequest, getAccessibleProjects } from "@/lib/dashboard-api";
import { requireSession } from "@/lib/server-session";
import { serviceConfig } from "@/lib/server-config";
import { selectAuthorizedProject } from "@/lib/role-access";
import type { Deployment, InfrastructureResource } from "@/types/api";
import WorkspaceEvidence from "./WorkspaceEvidence";

export default async function ProjectWorkspace({ mode, requested, offset }: {
  mode: "agent" | "drift"; requested?: string; offset?: string;
}) {
  const pageOffset = offset && /^\d{1,6}$/.test(offset) ? Number(offset) : 0;
  let more = false;
  const session = await requireSession();
  const projects = await getAccessibleProjects(session).then(({ data }) => data).catch(() => null);
  const project = selectAuthorizedProject(projects ?? [], requested);
  let items: (Deployment | InfrastructureResource)[] = [];
  let message = !projects ? "Project access unavailable." : "No authorized project selected.";
  if (project) {
    const audience = mode === "agent" ? "deployment" : "infrastructure";
    const collection = mode === "agent" ? "deployments" : "resources";
    const response = await backendRequest(session, audience,
      `${serviceConfig[audience]}/api/v1/${collection}?limit=100&offset=${pageOffset}`).catch(() => null);
    if (response?.ok) {
      const payload = await response.json().catch(() => null);
      const rows = payload?.items ?? payload?.data;
      if (Array.isArray(rows)) {
        more = rows.length === 100;
        items = rows.filter((row) => row && typeof row.id === "string" && row.project_id === project.id);
        message = items.length ? "" : "No records in this project on this page.";
      } else message = "Project records unavailable.";
    } else message = "Project records unavailable or access denied.";
  }
  const path = mode === "agent" ? "/agent" : "/drift";
  return <AppShell><section className="mx-auto max-w-5xl space-y-5 p-6">
    <h1 className="text-3xl font-semibold">{mode === "agent" ? "AI Kubernetes Agent" : "Terraform Drift"}</h1>
    <p>{mode === "agent" ? "Project-scoped evidence and deterministic diagnosis. Missing live evidence is unavailable, not a healthy result." : "Read-only observations, risk and history. Remediation requires a fresh plan and independent approval."}</p>
    {projects && projects.length > 0 && <form action={path} className="flex gap-3">
      <label>Project <select name="project" defaultValue={project?.id ?? ""} className="rounded border p-2">
        {!project && <option value="" disabled>Select an authorized project</option>}
        {projects.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}
      </select></label><button type="submit" className="rounded border px-3">Open project</button>
    </form>}
    {requested && !project && <p role="alert">Project unavailable or access denied.</p>}
    {message && <p role="status">{message}</p>}
    <WorkspaceEvidence key={`${mode}:${project?.id ?? "none"}`} mode={mode} items={items} role={session.role} />
    {project && <p className="text-sm">Showing up to 100 authorized records before project filtering. <Link className="underline" href={mode === "agent" ? "/deployments" : "/infrastructure"}>Open full workflow and audit history</Link></p>}
    {project && <nav aria-label="Project evidence pages" className="flex gap-4">
      {pageOffset > 0 && <Link className="underline" href={`${path}?project=${encodeURIComponent(project.id)}&offset=${Math.max(0,pageOffset-100)}`}>Previous records</Link>}
      {more && pageOffset < 999800 && <Link className="underline" href={`${path}?project=${encodeURIComponent(project.id)}&offset=${pageOffset+100}`}>Next records</Link>}
    </nav>}
    {session.role !== "developer" && mode === "agent" && <Link className="underline" href="/incidents">Incident analysis, RAG references and approval-gated remediation</Link>}
  </section></AppShell>;
}
