
import Link from "next/link";
import { requireSession } from "@/lib/server-session";
import { dashboardCapabilities, dashboardProfiles } from "@/lib/role-access";
import AppShell from "@/components/layout/AppShell";
import MetricCard from "@/components/dashboard/MetricCard";
import ServiceHealthGrid from "@/components/dashboard/ServiceHealthGrid";
import OperationalInsights from "@/components/dashboard/OperationalInsights";
import ActivityTimeline from "@/components/dashboard/ActivityTimeline";
import PlatformCommandCenter from "@/components/dashboard/PlatformCommandCenter";
import { getDashboardData } from "@/lib/dashboard-api";
import type { ServiceHealth } from "@/types/health";

export const dynamic = "force-dynamic";

const initialServices: ServiceHealth[] = [
  {
    name: "Project Service",
    description: "Project lifecycle management",
    port: 8080,
    status: "not-checked",
    latencyMs: null,
  },
  {
    name: "Infrastructure Service",
    description: "Infrastructure resource management",
    port: 8081,
    status: "not-checked",
    latencyMs: null,
  },
  {
    name: "Deployment Service",
    description: "Application deployment workflows",
    port: 8082,
    status: "not-checked",
    latencyMs: null,
  },
  {
    name: "AI-Ops Service",
    description: "Incident intelligence and analysis",
    port: 8090,
    status: "not-checked",
    latencyMs: null,
  },
  {
    name: "FinOps Service",
    description: "Cloud cost analysis and optimization",
    port: 8091,
    status: "not-checked",
    latencyMs: null,
  },
  {
    name: "Prometheus",
    description: "Metrics collection and querying",
    port: 9090,
    status: "not-checked",
    latencyMs: null,
  },
  {
    name: "Grafana",
    description: "Observability dashboards",
    port: 3001,
    status: "not-checked",
    latencyMs: null,
  },
];

function formatMetric(
  value: number | null,
  suffix = "",
  decimals = 2,
): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `${value.toFixed(decimals)}${suffix}`;
}

function formatRequestRate(
  value: number | null,
): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `${value.toFixed(3)}/s`;
}

function getAvailabilityDescription(
  availability: number | null,
): string {
  if (availability === null) {
    return "Prometheus availability metric unavailable";
  }

  return "Deployment Service availability";
}

function getErrorRateDescription(
  errorRate: number | null,
): string {
  if (errorRate === null) {
    return "Prometheus error-rate metric unavailable";
  }

  if (errorRate === 0) {
    return "No 5xx errors in the selected window";
  }

  return "HTTP 5xx error rate over the last 5 minutes";
}

export default async function DashboardPage() {
  const session = await requireSession();
  const dashboard = await getDashboardData(session);
  const profile = dashboardProfiles[session.role];
  const capabilities = dashboardCapabilities(session.role);
  const developer = session.role === "developer";
  const grafana = process.env.NEXT_PUBLIC_GRAFANA_URL;
  const grafanaLink = grafana && /^https?:\/\//i.test(grafana) ? grafana : null;
  const amount = dashboard.accountCost;
  const costValue = amount && /^[A-Z]{3}$/.test(amount.currency)
    ? new Intl.NumberFormat("en", { style: "currency", currency: amount.currency }).format(amount.amount)
    : "Unavailable";

  const count = (value: number | null) => value === null ? "Unavailable" : value >= 100 ? "100+" : String(value);

  const {
    metrics,
    observability,
    errors,
  } = dashboard;

  return (
    <AppShell>
      <div className="mx-auto max-w-[1600px] space-y-8 p-4 sm:p-6 lg:p-8">
        <section className="space-y-3">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{profile.title}</h1>
          <p className="max-w-2xl text-sm text-[var(--cf-text-secondary)]">{profile.description}</p>
          {developer && <Link href="/projects?create=1" className="inline-flex rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white">Create Project</Link>}
        </section>

        {errors.length > 0 && (
          <section className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
            <p className="text-sm font-semibold text-amber-700 dark:text-amber-300">
              Some dashboard data could not be loaded
            </p>

            <ul className="mt-2 space-y-1 text-xs text-amber-700 dark:text-amber-200">
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </section>
        )}

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {session.role !== "sre" && <MetricCard label={developer ? "My Projects" : "Projects"}
            value={count(metrics.projects)} description={developer ? "Projects shared with your account" : "Projects in the platform"} icon="◈" accent="indigo" />}
          <MetricCard label={developer ? "My Infrastructure" : "Infrastructure"}
            value={count(metrics.infrastructure)} description={developer ? "Resources and requests in your projects" : "Infrastructure resources"} icon="⌘" accent="emerald" />
          <MetricCard label={developer ? "My Deployments" : "Deployments"}
            value={count(metrics.deployments)} description={developer ? "Deployments in your projects" : "Platform deployments"} icon="⇧" accent="amber" />
          {capabilities.platformTelemetry && <MetricCard label="Incidents"
            value={count(metrics.incidents)} description="Incidents reported by AIOps" icon="⚡" accent="rose" />}
          {capabilities.approvalQueue && <MetricCard label="Pending Terraform approvals"
            value={count(dashboard.pendingApprovals)} description="Submitted, unexpired plans" icon="✓" accent="amber" />}
          {capabilities.accountCosts && <MetricCard label="AWS monthly cost"
            value={costValue} description="Actual cost reported by FinOps" icon="$" accent="emerald" />}
        </section>

        {developer && <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5">
          <h2 className="text-lg font-semibold">Project monitoring</h2>
          {metrics.projects === null ? <p className="mt-2 text-sm text-[var(--cf-text-muted)]">Projects could not be loaded.</p> :
            dashboard.projects.length === 0 ? <p className="mt-2 text-sm text-[var(--cf-text-muted)]">No projects available. Create one or ask a project owner for access.</p> :
            <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {dashboard.projects.slice(0, 6).map((project) => <li key={project.id}>
                <Link href={`/observability?project=${encodeURIComponent(project.id)}`} className="block rounded-lg border border-[var(--cf-border)] p-3 text-sm font-medium hover:border-indigo-500">
                  {project.name}<span className="ml-2 text-xs text-[var(--cf-text-muted)]">{project.access_level}</span>
                </Link>
              </li>)}
            </ul>}
        </section>}

        <PlatformCommandCenter role={session.role} />

        {capabilities.platformTelemetry && <>
        <section>
          <div className="mb-4">
            <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
              Live telemetry
            </p>

            <h3 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
              Observability metrics
            </h3>

            <p className="mt-1 text-sm text-[var(--cf-text-muted)]">
              Live Prometheus measurements from the Deployment Service.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <MetricCard
              label="Availability"
              value={formatMetric(
                observability.availability,
                "%",
              )}
              description={getAvailabilityDescription(
                observability.availability,
              )}
              icon="◉"
              accent="emerald"
            />

            <MetricCard
              label="Request Rate"
              value={formatRequestRate(
                observability.requestRate,
              )}
              description="Requests per second over the last 5 minutes"
              icon="↗"
              accent="indigo"
            />

            <MetricCard
              label="Error Rate"
              value={formatMetric(
                observability.errorRate,
                "%",
              )}
              description={getErrorRateDescription(
                observability.errorRate,
              )}
              icon="⚠"
              accent="rose"
            />

            <MetricCard
              label="P95 Latency"
              value={formatMetric(
                observability.p95Latency,
                " ms",
              )}
              description="95th percentile HTTP request latency"
              icon="◷"
              accent="amber"
            />

            <MetricCard
              label="Deployments in Progress"
              value={formatMetric(
                observability.deploymentsInProgress,
                "",
                0,
              )}
              description="Currently active deployments"
              icon="⇧"
              accent="indigo"
            />

            <MetricCard
              label="Requests in Flight"
              value={formatMetric(
                observability.requestsInFlight,
                "",
                0,
              )}
              description="Currently processing HTTP requests"
              icon="⇄"
              accent="emerald"
            />
          </div>
        </section>

        {grafanaLink && <Link href={grafanaLink}
          className="inline-flex rounded-lg border border-[var(--cf-border)] px-4 py-2 text-sm font-semibold">Open Grafana</Link>}

        <ServiceHealthGrid
          initialServices={initialServices}
        />

        <OperationalInsights
          observability={observability}
          incidentCount={metrics.incidents}
        />

        </>}

        <ActivityTimeline limit={10} includeIncidents={capabilities.platformTelemetry} />
      </div>
    </AppShell>
  );
}
