
import AppShell from "@/components/layout/AppShell";
import MetricCard from "@/components/dashboard/MetricCard";
import ServiceHealthGrid from "@/components/dashboard/ServiceHealthGrid";
import OperationalInsights from "@/components/dashboard/OperationalInsights";
import ActivityTimeline from "@/components/dashboard/ActivityTimeline";
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
  const dashboard = await getDashboardData();

  const {
    metrics,
    observability,
    errors,
  } = dashboard;

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

        <section>
          <div className="mb-4">
            <p className="text-sm font-medium text-indigo-400">
              Live telemetry
            </p>

            <h3 className="mt-1 text-xl font-semibold text-white">
              Observability metrics
            </h3>

            <p className="mt-1 text-sm text-zinc-500">
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

        <ServiceHealthGrid
          initialServices={initialServices}
        />

        <OperationalInsights
          observability={observability}
          incidentCount={metrics.incidents}
        />

        <ActivityTimeline limit={10} />
      </div>
    </AppShell>
  );
}
