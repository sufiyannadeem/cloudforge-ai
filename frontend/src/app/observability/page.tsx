"use client";

import { useCallback, useEffect, useState } from "react";

import AppShell from "@/components/layout/AppShell";
import {
  getDeploymentProgress,
  getP95Latency,
  getRequestRate,
  getRequestsInFlight,
  getServiceAvailability,
  getErrorRate,
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

type MetricCardProps = {
  title: string;
  value: string;
  description: string;
  icon: string;
  accentClass: string;
};

function MetricCard({
  title,
  value,
  description,
  icon,
  accentClass,
}: MetricCardProps) {
  return (
    <div className="rounded-xl border border-[#29292f] bg-[#121214] p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm font-medium text-gray-400">{title}</p>

        <div
          className={`flex h-10 w-10 items-center justify-center rounded-xl text-lg ${accentClass}`}
        >
          {icon}
        </div>
      </div>

      <p className="mt-6 text-3xl font-semibold tracking-tight text-white">
        {value}
      </p>

      <p className="mt-2 text-sm leading-6 text-gray-500">{description}</p>
    </div>
  );
}

function formatMetric(
  value: MetricValue,
  suffix = "",
  decimals = 2,
): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `${value.toFixed(decimals)}${suffix}`;
}

function formatCount(value: MetricValue): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return Math.round(value).toString();
}

export default function ObservabilityPage() {
  const [metrics, setMetrics] =
    useState<ObservabilityMetrics>(EMPTY_METRICS);

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadMetrics = useCallback(async (manualRefresh = false) => {
    if (manualRefresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    setError(null);

    const results = await Promise.allSettled([
      getServiceAvailability(),
      getRequestRate(),
      getErrorRate(),
      getP95Latency(),
      getDeploymentProgress(),
      getRequestsInFlight(),
    ]);

    const [
      availabilityResult,
      requestRateResult,
      errorRateResult,
      p95LatencyResult,
      deploymentsInProgressResult,
      requestsInFlightResult,
    ] = results;

    const getValue = (
      result: PromiseSettledResult<number | null>,
    ): number | null => {
      if (result.status === "fulfilled") {
        return result.value;
      }

      return null;
    };

    const failedMetrics = results.filter(
      (result) => result.status === "rejected",
    ).length;

    setMetrics({
      availability: getValue(availabilityResult),
      requestRate: getValue(requestRateResult),
      errorRate: getValue(errorRateResult),
      p95Latency: getValue(p95LatencyResult),
      deploymentsInProgress: getValue(deploymentsInProgressResult),
      requestsInFlight: getValue(requestsInFlightResult),
    });

    if (failedMetrics > 0) {
      setError(
        `${failedMetrics} observability metric${
          failedMetrics === 1 ? "" : "s"
        } could not be loaded from Prometheus.`,
      );
    }

    setLastUpdated(new Date());
    setIsLoading(false);
    setIsRefreshing(false);
  }, []);

  useEffect(() => {
    // Initial data loading is intentionally triggered when the page mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMetrics();

    const interval = window.setInterval(() => {
      void loadMetrics(true);
    }, 15000);

    return () => {
      window.clearInterval(interval);
    };
  }, [loadMetrics]);

  const reliabilityStatus =
    metrics.availability !== null &&
    metrics.errorRate !== null &&
    metrics.availability >= 99.9 &&
    metrics.errorRate < 1
      ? "Healthy"
      : "Needs attention";

  return (
    <AppShell>
      <main className="min-w-0 space-y-8 bg-[#09090b] p-4 text-gray-100 md:p-6">
        <section className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
          <div>
            <p className="text-sm font-medium text-indigo-400">
              Platform observability
            </p>

            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">
              Observability
            </h1>

            <p className="mt-3 max-w-3xl text-sm leading-6 text-gray-400">
              Monitor live service reliability, request traffic, latency,
              and deployment activity using Prometheus metrics.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void loadMetrics(true)}
            disabled={isRefreshing}
            className="rounded-lg border border-[#3b3b44] bg-[#151519] px-4 py-2 text-sm font-medium text-gray-200 transition hover:border-indigo-400 hover:bg-[#1c1c24] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRefreshing ? "Refreshing..." : "Refresh metrics"}
          </button>
        </section>

        <section className="rounded-xl border border-[#29292f] bg-[#121214] p-5">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div>
              <p className="text-sm text-gray-400">Monitoring target</p>
              <h2 className="mt-1 text-lg font-semibold text-white">
                Deployment Service
              </h2>
            </div>

            <div className="flex items-center gap-2 text-sm text-gray-400">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              Prometheus
            </div>
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-lg bg-[#1a1a1f] p-4">
              <p className="text-xs uppercase tracking-wide text-gray-500">
                Reliability status
              </p>

              <p
                className={`mt-2 text-lg font-semibold ${
                  reliabilityStatus === "Healthy"
                    ? "text-emerald-400"
                    : "text-amber-400"
                }`}
              >
                {isLoading ? "Loading..." : reliabilityStatus}
              </p>
            </div>

            <div className="rounded-lg bg-[#1a1a1f] p-4">
              <p className="text-xs uppercase tracking-wide text-gray-500">
                Refresh interval
              </p>

              <p className="mt-2 text-lg font-semibold text-white">
                15 seconds
              </p>
            </div>

            <div className="rounded-lg bg-[#1a1a1f] p-4">
              <p className="text-xs uppercase tracking-wide text-gray-500">
                Last updated
              </p>

              <p className="mt-2 text-sm font-semibold text-white">
                {lastUpdated
                  ? lastUpdated.toLocaleTimeString()
                  : "Not available"}
              </p>
            </div>
          </div>
        </section>

        {error && (
          <div className="rounded-xl border border-amber-700/60 bg-amber-950/30 p-4 text-sm text-amber-300">
            {error}
          </div>
        )}

        <section>
          <div className="mb-4">
            <p className="text-sm font-medium text-indigo-400">
              Service-level indicators
            </p>

            <h2 className="mt-1 text-2xl font-semibold text-white">
              Live metrics
            </h2>

            <p className="mt-2 text-sm text-gray-500">
              Values are calculated from the current Prometheus measurement
              window.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <MetricCard
              title="Availability"
              value={formatMetric(metrics.availability, "%")}
              description="Percentage of healthy Deployment Service targets."
              icon="◉"
              accentClass="bg-emerald-950/60 text-emerald-400"
            />

            <MetricCard
              title="Request Rate"
              value={formatMetric(metrics.requestRate, "/s", 3)}
              description="Average HTTP requests per second during the last five minutes."
              icon="↗"
              accentClass="bg-indigo-950/60 text-indigo-400"
            />

            <MetricCard
              title="Error Rate"
              value={formatMetric(metrics.errorRate, "%")}
              description="Percentage of HTTP 5xx responses during the last five minutes."
              icon="△"
              accentClass="bg-rose-950/60 text-rose-400"
            />

            <MetricCard
              title="P95 Latency"
              value={formatMetric(metrics.p95Latency, " ms")}
              description="95th percentile HTTP request latency."
              icon="◷"
              accentClass="bg-amber-950/60 text-amber-400"
            />

            <MetricCard
              title="Deployments in Progress"
              value={formatCount(metrics.deploymentsInProgress)}
              description="Number of currently active deployment operations."
              icon="↑"
              accentClass="bg-indigo-950/60 text-indigo-400"
            />

            <MetricCard
              title="Requests in Flight"
              value={formatCount(metrics.requestsInFlight)}
              description="HTTP requests currently being processed."
              icon="⇄"
              accentClass="bg-emerald-950/60 text-emerald-400"
            />
          </div>
        </section>

        <section className="rounded-xl border border-[#29292f] bg-[#121214] p-5">
          <p className="text-sm font-medium text-indigo-400">
            SRE reference
          </p>

          <h2 className="mt-1 text-xl font-semibold text-white">
            Reliability interpretation
          </h2>

          <div className="mt-5 space-y-4 text-sm leading-6 text-gray-400">
            <p>
              <span className="font-medium text-gray-200">
                Availability:
              </span>{" "}
              Measures whether the monitored service target is reachable and
              healthy.
            </p>

            <p>
              <span className="font-medium text-gray-200">
                Error rate:
              </span>{" "}
              Shows the proportion of server-side HTTP 5xx responses.
            </p>

            <p>
              <span className="font-medium text-gray-200">
                P95 latency:
              </span>{" "}
              Represents the response time below which approximately 95% of
              observed requests completed.
            </p>

            <p>
              <span className="font-medium text-gray-200">
                SLO reference:
              </span>{" "}
              A 99.9% availability target is used as a comparison reference.
              A formal error budget requires a defined measurement period and
              historical availability data.
            </p>
          </div>
        </section>

        <section className="rounded-xl border border-[#29292f] bg-[#121214] p-5">
          <h2 className="text-xl font-semibold text-white">
            Prometheus queries
          </h2>

          <p className="mt-2 text-sm text-gray-500">
            The page uses the internal Next.js observability API route rather
            than exposing Prometheus directly to the browser.
          </p>

          <div className="mt-5 space-y-3">
            {[
              "avg(up{job=\"deployment-service\"}) * 100",
              "sum(rate(http_requests_total{job=\"deployment-service\"}[5m]))",
              "sum(rate(http_requests_total{job=\"deployment-service\",status=~\"5..\"}[5m])) / sum(rate(http_requests_total{job=\"deployment-service\"}[5m])) * 100",
              "histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job=\"deployment-service\"}[5m]))) * 1000",
              "cloudforge_deployments_in_progress",
              "http_requests_in_flight",
            ].map((query) => (
              <div
                key={query}
                className="overflow-x-auto rounded-lg bg-[#1a1a1f] px-4 py-3"
              >
                <code className="whitespace-pre text-xs text-gray-300">
                  {query}
                </code>
              </div>
            ))}
          </div>
        </section>
      </main>
    </AppShell>
  );
}
