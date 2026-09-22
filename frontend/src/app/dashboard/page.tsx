import AppShell from "@/components/layout/AppShell";
import MetricCard from "@/components/dashboard/MetricCard";
import ServiceHealthGrid from "@/components/dashboard/ServiceHealthGrid";
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
    name: "Prometheus",
    description: "Metrics collection and querying",
    port: 9090,
    status: "not-checked",
    latencyMs: null,
  },
  {
    name: "Grafana",
    description: "Observability dashboards",
    port: 3000,
    status: "not-checked",
    latencyMs: null,
  },
];

export default async function DashboardPage() {
  const dashboard = await getDashboardData();

  const { metrics, errors } = dashboard;

  return (
    <AppShell>
      <div className="mx-auto max-w-[1600px] space-y-8 p-4 sm:p-6 lg:p-8">
        <section className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <p className="mb-2 text-sm font-medium text-indigo-400">
              Platform overview
            </p>

            <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
              Welcome to CloudForge
            </h2>

            <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-400">
              Monitor your projects, infrastructure, deployments,
              and AI-powered incident intelligence.
            </p>
          </div>

          <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
            <p className="text-xs text-zinc-500">
              Environment
            </p>

            <p className="mt-1 text-sm font-semibold text-white">
              Development
            </p>
          </div>
        </section>

        {errors.length > 0 && (
          <section className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
            <p className="text-sm font-semibold text-amber-300">
              Some dashboard data could not be loaded
            </p>

            <ul className="mt-2 space-y-1 text-xs text-amber-200">
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </section>
        )}

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Projects"
            value={String(metrics.projects)}
            description="Projects returned by Project Service"
            icon="◈"
            accent="indigo"
          />

          <MetricCard
            label="Infrastructure Resources"
            value={String(metrics.infrastructure)}
            description="Resources returned by Infrastructure Service"
            icon="⌘"
            accent="emerald"
          />

          <MetricCard
            label="Deployments"
            value={String(metrics.deployments)}
            description="Deployments returned by Deployment Service"
            icon="⇧"
            accent="amber"
          />

          <MetricCard
            label="Incidents"
            value={String(metrics.incidents)}
            description="Incidents returned by AI-Ops Service"
            icon="⚡"
            accent="rose"
          />
        </section>

        <ServiceHealthGrid
          initialServices={initialServices}
        />

        <section className="grid gap-6 xl:grid-cols-2">
          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6">
            <h3 className="text-lg font-semibold text-white">
              Recent activity
            </h3>

            <p className="mt-1 text-sm text-zinc-500">
              Activity timeline integration will be added with the
              incident and deployment pages.
            </p>

            <div className="mt-6 rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-center">
              <p className="text-sm text-zinc-500">
                No activity loaded yet
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6">
            <h3 className="text-lg font-semibold text-white">
              Reliability overview
            </h3>

            <p className="mt-1 text-sm text-zinc-500">
              SLO and Prometheus metrics will be integrated in the
              observability module.
            </p>

            <div className="mt-6 space-y-4">
              <div className="flex items-center justify-between rounded-xl bg-zinc-900 px-4 py-3">
                <span className="text-sm text-zinc-400">
                  Availability
                </span>

                <span className="text-sm text-zinc-500">
                  Not measured
                </span>
              </div>

              <div className="flex items-center justify-between rounded-xl bg-zinc-900 px-4 py-3">
                <span className="text-sm text-zinc-400">
                  Error budget
                </span>

                <span className="text-sm text-zinc-500">
                  Not measured
                </span>
              </div>

              <div className="flex items-center justify-between rounded-xl bg-zinc-900 px-4 py-3">
                <span className="text-sm text-zinc-400">
                  Active alerts
                </span>

                <span className="text-sm text-zinc-500">
                  Not measured
                </span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
