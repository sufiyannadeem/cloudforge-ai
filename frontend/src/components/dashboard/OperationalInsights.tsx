"use client";

import { useEffect, useState } from "react";
import type { DashboardObservability } from "@/types/dashboard";

interface OperationalInsightsProps {
  observability: DashboardObservability;
  incidentCount: number;
}

interface IncidentStats {
  total_incidents: number;
  open_incidents: number;
  resolved_incidents: number;
  total_alerts: number;
  average_alerts_per_incident: number;
}

interface Deployment {
  id: string;
  project_id: string;
  environment: string;
  image: string;
  git_commit_sha: string;
  namespace: string;
  status: string;
  created_at: string;
  updated_at: string;
}

interface DeploymentListResponse {
  items?: Deployment[];
  data?: Deployment[];
}

interface OperationalData {
  incidentStats: IncidentStats | null;
  deployments: Deployment[];
}

const initialOperationalData: OperationalData = {
  incidentStats: null,
  deployments: [],
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

function formatDate(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }

  return date.toLocaleString();
}

function getReliabilityStatus(
  availability: number | null,
  errorRate: number | null,
): {
  label: string;
  className: string;
} {
  if (availability === null || errorRate === null) {
    return {
      label: "Unknown",
      className:
        "border-[var(--cf-border)] bg-[var(--cf-surface-2)] text-[var(--cf-text-secondary)]",
    };
  }

  if (availability < 99 || errorRate > 5) {
    return {
      label: "Degraded",
      className:
        "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300",
    };
  }

  return {
    label: "Healthy",
    className:
      "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  };
}

function getDeploymentStatusClass(
  status: string,
): string {
  switch (status.toLowerCase()) {
    case "succeeded":
      return "text-emerald-600 dark:text-emerald-400";

    case "failed":
      return "text-rose-600 dark:text-rose-400";

    case "running":
    case "queued":
    case "pending":
      return "text-amber-600 dark:text-amber-400";

    case "cancelled":
      return "text-[var(--cf-text-secondary)]";

    default:
      return "text-indigo-600 dark:text-indigo-400";
  }
}

async function fetchJson<T>(
  url: string,
): Promise<T> {
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(
      `Request failed with status ${response.status}`,
    );
  }

  return response.json() as Promise<T>;
}

export default function OperationalInsights({
  observability,
  incidentCount,
}: OperationalInsightsProps) {
  const [data, setData] = useState<OperationalData>(
    initialOperationalData,
  );

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadOperationalData() {
      setLoading(true);
      setError(null);

      const [incidentResult, deploymentResult] =
        await Promise.allSettled([
          fetchJson<IncidentStats>(
            "/api/proxy/aiops/api/v1/incidents/stats",
          ),
          fetchJson<DeploymentListResponse>(
            "/api/proxy/deployment/api/v1/deployments?limit=5&offset=0",
          ),
        ]);

      if (!isMounted) {
        return;
      }

      const errors: string[] = [];

      let incidentStats: IncidentStats | null = null;
      let deployments: Deployment[] = [];

      if (incidentResult.status === "fulfilled") {
        incidentStats = incidentResult.value;
      } else {
        errors.push("Incident statistics unavailable");
      }

      if (deploymentResult.status === "fulfilled") {
        deployments =
          deploymentResult.value.items ??
          deploymentResult.value.data ??
          [];
      } else {
        errors.push("Recent deployments unavailable");
      }

      setData({
        incidentStats,
        deployments,
      });

      setError(
        errors.length > 0 ? errors.join(" • ") : null,
      );

      setLoading(false);
    }

    void loadOperationalData();

    return () => {
      isMounted = false;
    };
  }, []);

  const reliabilityStatus = getReliabilityStatus(
    observability.availability,
    observability.errorRate,
  );

  const incidentStats = data.incidentStats;

  return (
    <section className="space-y-6">
      <div>
        <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
          Operational intelligence
        </p>

        <h3 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
          Reliability and activity
        </h3>

        <p className="mt-1 text-sm text-[var(--cf-text-muted)]">
          Current reliability signals, incident posture,
          and recent deployment activity.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-300">
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h4 className="text-lg font-semibold text-[var(--cf-text)]">
                Reliability posture
              </h4>

              <p className="mt-1 text-sm text-[var(--cf-text-muted)]">
                Current Prometheus measurement window
              </p>
            </div>

            <span
              className={`rounded-full border px-3 py-1 text-xs font-semibold ${reliabilityStatus.className}`}
            >
              {reliabilityStatus.label}
            </span>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
              <p className="text-xs text-[var(--cf-text-muted)]">
                Availability
              </p>

              <p className="mt-2 text-2xl font-semibold text-[var(--cf-text)]">
                {formatNumber(observability.availability)}%
              </p>
            </div>

            <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
              <p className="text-xs text-[var(--cf-text-muted)]">
                Error rate
              </p>

              <p className="mt-2 text-2xl font-semibold text-[var(--cf-text)]">
                {formatNumber(observability.errorRate)}%
              </p>
            </div>

            <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
              <p className="text-xs text-[var(--cf-text-muted)]">
                P95 latency
              </p>

              <p className="mt-2 text-2xl font-semibold text-[var(--cf-text)]">
                {formatNumber(observability.p95Latency)} ms
              </p>
            </div>

            <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
              <p className="text-xs text-[var(--cf-text-muted)]">
                SLO reference
              </p>

              <p className="mt-2 text-2xl font-semibold text-[var(--cf-text)]">
                99.9%
              </p>
            </div>
          </div>

          <p className="mt-4 text-xs leading-5 text-[var(--cf-text-muted)]">
            The SLO reference is a target for comparison.
            A formal error budget requires a defined time
            window and historical availability measurements.
          </p>
        </div>

        <div className="rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-sm">
          <div>
            <h4 className="text-lg font-semibold text-[var(--cf-text)]">
              Incident summary
            </h4>

            <p className="mt-1 text-sm text-[var(--cf-text-muted)]">
              Data provided by the AI-Ops Service
            </p>
          </div>

          {loading && !incidentStats ? (
            <div className="mt-6 rounded-xl bg-[var(--cf-surface-2)] p-6 text-center text-sm text-[var(--cf-text-muted)]">
              Loading incident statistics...
            </div>
          ) : (
            <div className="mt-6 grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
                <p className="text-xs text-[var(--cf-text-muted)]">
                  Total incidents
                </p>

                <p className="mt-2 text-2xl font-semibold text-[var(--cf-text)]">
                  {incidentStats?.total_incidents ??
                    incidentCount}
                </p>
              </div>

              <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
                <p className="text-xs text-[var(--cf-text-muted)]">
                  Open incidents
                </p>

                <p className="mt-2 text-2xl font-semibold text-rose-400">
                  {incidentStats?.open_incidents ?? "N/A"}
                </p>
              </div>

              <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
                <p className="text-xs text-[var(--cf-text-muted)]">
                  Resolved incidents
                </p>

                <p className="mt-2 text-2xl font-semibold text-emerald-400">
                  {incidentStats?.resolved_incidents ?? "N/A"}
                </p>
              </div>

              <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
                <p className="text-xs text-[var(--cf-text-muted)]">
                  Total alerts
                </p>

                <p className="mt-2 text-2xl font-semibold text-amber-400">
                  {incidentStats?.total_alerts ?? "N/A"}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-sm">
        <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
          <div>
            <h4 className="text-lg font-semibold text-[var(--cf-text)]">
              Recent deployments
            </h4>

            <p className="mt-1 text-sm text-[var(--cf-text-muted)]">
              Latest deployment records from Deployment Service
            </p>
          </div>

          <span className="text-xs text-[var(--cf-text-muted)]">
            Showing up to 5 records
          </span>
        </div>

        {loading && data.deployments.length === 0 ? (
          <div className="mt-6 rounded-xl bg-[var(--cf-surface-2)] p-6 text-center text-sm text-[var(--cf-text-muted)]">
            Loading recent deployments...
          </div>
        ) : data.deployments.length === 0 ? (
          <div className="mt-6 rounded-xl border border-dashed border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-6 text-center text-sm text-[var(--cf-text-muted)]">
            No deployments available
          </div>
        ) : (
          <div className="mt-6 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-[var(--cf-border)] text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
                <tr>
                  <th className="px-3 py-3 font-medium">
                    Environment
                  </th>

                  <th className="px-3 py-3 font-medium">
                    Image
                  </th>

                  <th className="px-3 py-3 font-medium">
                    Status
                  </th>

                  <th className="px-3 py-3 font-medium">
                    Created
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-zinc-800">
                {data.deployments.map((deployment) => (
                  <tr key={deployment.id}>
                    <td className="whitespace-nowrap px-3 py-4 text-[var(--cf-text-secondary)]">
                      {deployment.environment}
                    </td>

                    <td className="max-w-[220px] truncate px-3 py-4 text-[var(--cf-text-secondary)]">
                      {deployment.image}
                    </td>

                    <td
                      className={`whitespace-nowrap px-3 py-4 font-medium ${getDeploymentStatusClass(
                        deployment.status,
                      )}`}
                    >
                      {deployment.status}
                    </td>

                    <td className="whitespace-nowrap px-3 py-4 text-[var(--cf-text-muted)]">
                      {formatDate(deployment.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
