"use client";

import { useCallback, useEffect, useState } from "react";

import AppShell from "@/components/layout/AppShell";
import {
  getDeploymentProgress,
  getErrorRate,
  getP95Latency,
  getRequestRate,
  getRequestsInFlight,
  getServiceAvailability,
} from "@/lib/observability-api";

type MetricValue = number | null;

type ObservabilityMetrics = {
  availability: MetricValue;
  requestRate: MetricValue;
  errorRate: MetricValue;
  p95Latency: MetricValue;
  deploymentsInProgress: MetricValue;
  requestsInFlight: MetricValue;
};

const EMPTY_METRICS: ObservabilityMetrics = {
  availability: null,
  requestRate: null,
  errorRate: null,
  p95Latency: null,
  deploymentsInProgress: null,
  requestsInFlight: null,
};

function formatNumber(
  value: number | null,
  decimals = 2,
): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return value.toFixed(decimals);
}

function formatPercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `${value.toFixed(2)}%`;
}

function MetricCard({
  title,
  value,
  description,
  icon,
  accentClass,
}: {
  title: string;
  value: string;
  description: string;
  icon: string;
  accentClass: string;
}) {
  return (
    <article className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-[var(--cf-text-secondary)]">
            {title}
          </p>

          <p className="mt-2 text-3xl font-bold tracking-tight text-[var(--cf-text)]">
            {value}
          </p>
        </div>

        <span
          className={`flex h-10 w-10 items-center justify-center rounded-lg ${accentClass}`}
        >
          {icon}
        </span>
      </div>

      <p className="mt-3 text-xs leading-5 text-[var(--cf-text-muted)]">
        {description}
      </p>
    </article>
  );
}

export default function ObservabilityPage() {
  const [metrics, setMetrics] =
    useState<ObservabilityMetrics>(EMPTY_METRICS);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(
    null,
  );

  const loadMetrics = useCallback(async () => {
    const [
      availability,
      requestRate,
      errorRate,
      p95Latency,
      deploymentsInProgress,
      requestsInFlight,
    ] = await Promise.all([
      getServiceAvailability(),
      getRequestRate(),
      getErrorRate(),
      getP95Latency(),
      getDeploymentProgress(),
      getRequestsInFlight(),
    ]);

    setMetrics({
      availability,
      requestRate,
      errorRate,
      p95Latency,
      deploymentsInProgress,
      requestsInFlight,
    });

    setLastUpdated(new Date().toLocaleTimeString());
    setIsLoading(false);
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void loadMetrics();
    }, 30_000);

    return () => {
      window.clearInterval(interval);
    };
  }, [loadMetrics]);

  const refreshOnMount = useCallback(() => {
    void loadMetrics();
  }, [loadMetrics]);

  useEffect(() => {
    const timeout = window.setTimeout(refreshOnMount, 0);

    return () => {
      window.clearTimeout(timeout);
    };
  }, [refreshOnMount]);

  return (
    <AppShell>
      <main className="min-w-0 space-y-6 bg-[var(--cf-background)] p-4 text-[var(--cf-text)] md:p-6">
        <header className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
              Platform observability
            </p>

            <h1 className="mt-1 text-3xl font-bold tracking-tight text-[var(--cf-text)]">
              Service telemetry
            </h1>

            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--cf-text-secondary)]">
              Live operational signals derived from the CloudForge
              Prometheus recording rules.
            </p>
          </div>

          <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-3 py-2 text-xs text-[var(--cf-text-muted)]">
            {isLoading
              ? "Refreshing telemetry..."
              : `Updated ${lastUpdated ?? "just now"}`}
          </div>
        </header>

        <section>
          <div className="mb-4">
            <h2 className="text-xl font-semibold text-[var(--cf-text)]">
              Golden signals
            </h2>

            <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
              Availability, traffic, errors and latency for the
              deployment service.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              title="Availability"
              value={formatPercent(metrics.availability)}
              description="Current service availability percentage."
              icon="✓"
              accentClass="bg-emerald-500/10 text-emerald-600 dark:text-emerald-300"
            />

            <MetricCard
              title="Request rate"
              value={`${formatNumber(metrics.requestRate)} req/s`}
              description="Five-minute HTTP request rate."
              icon="↗"
              accentClass="bg-blue-500/10 text-blue-600 dark:text-blue-300"
            />

            <MetricCard
              title="Error rate"
              value={formatPercent(metrics.errorRate)}
              description="Five-minute HTTP error percentage."
              icon="!"
              accentClass="bg-rose-500/10 text-rose-600 dark:text-rose-300"
            />

            <MetricCard
              title="P95 latency"
              value={`${formatNumber(metrics.p95Latency)} ms`}
              description="Five-minute P95 request latency."
              icon="◷"
              accentClass="bg-amber-500/10 text-amber-600 dark:text-amber-300"
            />
          </div>
        </section>

        <section>
          <div className="mb-4">
            <h2 className="text-xl font-semibold text-[var(--cf-text)]">
              Platform activity
            </h2>

            <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
              Current work and request pressure across the service.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <MetricCard
              title="Deployments in progress"
              value={formatNumber(
                metrics.deploymentsInProgress,
                0,
              )}
              description="Deployments currently in an active execution state."
              icon="⇄"
              accentClass="bg-purple-500/10 text-purple-600 dark:text-purple-300"
            />

            <MetricCard
              title="Requests in flight"
              value={formatNumber(metrics.requestsInFlight, 0)}
              description="HTTP requests currently being processed."
              icon="◌"
              accentClass="bg-indigo-500/10 text-indigo-600 dark:text-indigo-300"
            />
          </div>
        </section>

        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
          <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
            SRE interpretation
          </p>

          <h2 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
            Operational signal guide
          </h2>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
              <p className="font-medium text-[var(--cf-text)]">
                Availability
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--cf-text-secondary)]">
                Measures whether the service is reachable and
                serving successfully.
              </p>
            </div>

            <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
              <p className="font-medium text-[var(--cf-text)]">
                Error rate
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--cf-text-secondary)]">
                Shows the percentage of HTTP requests returning
                server-side errors.
              </p>
            </div>

            <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
              <p className="font-medium text-[var(--cf-text)]">
                P95 latency
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--cf-text-secondary)]">
                Highlights the latency experienced by the slower
                five percent of requests.
              </p>
            </div>

            <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
              <p className="font-medium text-[var(--cf-text)]">
                In-flight pressure
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--cf-text-secondary)]">
                Helps identify increasing request or deployment
                concurrency before it becomes an incident.
              </p>
            </div>
          </div>
        </section>
      </main>
    </AppShell>
  );
}
