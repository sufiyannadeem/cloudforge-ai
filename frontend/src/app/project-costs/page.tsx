import { selectAuthorizedProject } from "@/lib/role-access";
import ProjectInsights from "@/components/finops/ProjectInsights";
import AppShell from "@/components/layout/AppShell";
import { backendRequest, getAccessibleProjects } from "@/lib/dashboard-api";
import { serviceConfig } from "@/lib/server-config";
import { requireSession } from "@/lib/server-session";

type ProjectCosts = {
  project_id: string;
  status: string;
  costs: { status: "actual" | "estimated"; currency: string; amount: string }[];
  history?: { date: string; status: "actual" | "estimated"; currency: string; amount: string }[];
  resources_with_cost: number;
  active_ec2_resources: number;
};

export default async function ProjectCostsPage({ searchParams }: { searchParams: Promise<{ project?: string }> }) {
  const session = await requireSession();

  const projects = await getAccessibleProjects(session).then(({ data }) => data).catch(() => null);
  const requested = (await searchParams).project;
  const project = selectAuthorizedProject(projects ?? [], requested);
  let costs: ProjectCosts | null = null;
  let message = "No authorized projects are available.";
  if (!projects) message = "Projects could not be loaded.";
  else if (requested && !project) message = "This project is unavailable or access was denied.";
  else if (project) {
    const response = await backendRequest(session, "finops",
      `${serviceConfig.finops}/api/v1/finops/projects/${encodeURIComponent(project.id)}/costs`).catch(() => null);
    if (response?.ok) {
      const data: ProjectCosts | null = await response.json().catch(() => null);
      if (data?.project_id === project.id && data.status === "available" && Array.isArray(data.costs) && data.costs.length) costs = data;
    }
    message = response?.status === 403 || response?.status === 404
      ? "This project is unavailable or access was denied."
      : "Verified AWS costs are unavailable for this project.";
  }

  return (
    <AppShell>
      <section className="mx-auto max-w-3xl space-y-4 p-6 sm:p-8">
        <h1 className="text-3xl font-semibold">Project FinOps</h1>
        {projects && projects.length > 0 && <form action="/project-costs" className="flex flex-wrap items-end gap-3">
          <label className="grid gap-2 text-sm">Project
            <select name="project" defaultValue={project?.id ?? ""} className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-2">
              {!project && <option value="" disabled>Select a project</option>}
              {projects.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}
            </select>
          </label>
          <button type="submit" className="rounded-lg border border-[var(--cf-border)] px-3 py-2 text-sm font-medium">View project costs</button>
        </form>}
        {session.role !== "developer" && <a href="/finops" className="underline">Account attribution, anomalies, optimization and trends</a>}
        {costs ? <section className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-4">
          <h2 className="font-semibold">Verified EC2 costs</h2>
          <p className="text-sm">Last seven complete UTC days. Billing records cover {costs.resources_with_cost} of {costs.active_ec2_resources} active EC2 resources.</p>
          <ul className="mt-3 space-y-2">
            {costs.costs.map(({ status, currency, amount }) => (
              <li key={`${status}-${currency}`}>{status === "actual" ? "Actual" : "Estimated"} · {amount} {currency}</li>
            ))}
          </ul>
          <h3 className="mt-4 font-semibold">Project cost history</h3>
          {costs.history?.length ? <table className="mt-2 w-full text-left text-sm"><caption>Attributed EC2 billing only; missing days are unavailable, not zero.</caption><thead><tr><th>UTC day</th><th>Quality</th><th>Amount</th></tr></thead><tbody>{costs.history.map((day) => <tr key={`${day.date}-${day.status}-${day.currency}`}><td>{day.date}</td><td>{day.status}</td><td>{day.amount} {day.currency}</td></tr>)}</tbody></table> : <p>Project trends unavailable.</p>}
        </section> : <p role="status" className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-4 text-sm">{message}</p>}
        {project && <ProjectInsights key={project.id} projectId={project.id} />}
      </section>
    </AppShell>
  );
}
