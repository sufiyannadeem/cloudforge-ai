"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type ActivityType = "deployment" | "incident";

interface Deployment {
  id: string;
  environment: string;
  image: string;
  status: string;
  created_at: string;
}

interface Incident {
  id: string;
  alert_name: string;
  service: string;
  severity: string;
  priority?: string;
  status: string;
  summary: string;
  created_at: string;
  updated_at: string;
}

interface DeploymentResponse {
  items?: Deployment[];
  data?: Deployment[];
}

interface IncidentResponse {
  incidents?: Incident[];
  items?: Incident[];
  data?: Incident[];
}

interface ActivityItem {
  id: string;
  type: ActivityType;
  title: string;
  description: string;
  status: string;
  severity?: string;
  priority?: string;
  timestamp: string;
  href?: string;
}

interface ActivityTimelineProps {
  limit?: number;
}

function formatDate(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Unknown time";
  }

  return date.toLocaleString();
}

function getStatusClass(status: string): string {
  switch (status.toLowerCase()) {
    case "succeeded":
    case "resolved":
    case "healthy":
      return "text-emerald-400";

    case "failed":
    case "critical":
      return "text-rose-400";

    case "running":
    case "queued":
    case "pending":
    case "warning":
      return "text-amber-400";

    case "acknowledged":
    case "assigned":
      return "text-indigo-400";

    default:
      return "text-zinc-400";
  }
}

function getSeverityClass(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical":
      return "border-rose-500/30 bg-rose-500/10 text-rose-300";

    case "warning":
      return "border-amber-500/30 bg-amber-500/10 text-amber-300";

    case "high":
      return "border-orange-500/30 bg-orange-500/10 text-orange-300";

    case "medium":
      return "border-indigo-500/30 bg-indigo-500/10 text-indigo-300";

    default:
      return "border-zinc-700 bg-zinc-800 text-zinc-300";
  }
}

function getActivityIcon(type: ActivityType): string {
  return type === "deployment" ? "⇧" : "⚡";
}

async function fetchJson<T>(url: string): Promise<T> {
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

function createActivityItems(
  deployments: Deployment[],
  incidents: Incident[],
): ActivityItem[] {
  const deploymentActivities: ActivityItem[] =
    deployments.map((deployment) => ({
      id: `deployment-${deployment.id}`,
      type: "deployment",
      title: `Deployment ${deployment.status}`,
      description: `${deployment.environment} · ${deployment.image}`,
      status: deployment.status,
      timestamp: deployment.created_at,
    }));

  const incidentActivities: ActivityItem[] =
    incidents.map((incident) => ({
      id: `incident-${incident.id}`,
      type: "incident",
      title: incident.alert_name,
      description:
        incident.summary ||
        `${incident.service} incident detected`,
      status: incident.status,
      severity: incident.severity,
      priority: incident.priority,
      timestamp: incident.updated_at || incident.created_at,
      href: `/incidents/${incident.id}`,
    }));

  return [
    ...deploymentActivities,
    ...incidentActivities,
  ]
    .sort(
      (first, second) =>
        new Date(second.timestamp).getTime() -
        new Date(first.timestamp).getTime(),
    )
    .slice(0, 10);
}

export default function ActivityTimeline({
  limit = 10,
}: ActivityTimelineProps) {
  const [activities, setActivities] = useState<ActivityItem[]>(
    [],
  );

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadActivities = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [deploymentResult, incidentResult] =
      await Promise.allSettled([
        fetchJson<DeploymentResponse>(
          "/api/proxy/deployment/api/v1/deployments?limit=10&offset=0",
        ),
        fetchJson<IncidentResponse>(
          "/api/proxy/aiops/api/v1/incidents?limit=10&offset=0",
        ),
      ]);

    const errors: string[] = [];

    let deployments: Deployment[] = [];
    let incidents: Incident[] = [];

    if (deploymentResult.status === "fulfilled") {
      deployments =
        deploymentResult.value.items ??
        deploymentResult.value.data ??
        [];
    } else {
      errors.push("Deployments unavailable");
    }

    if (incidentResult.status === "fulfilled") {
      incidents =
        incidentResult.value.incidents ??
        incidentResult.value.items ??
        incidentResult.value.data ??
        [];
    } else {
      errors.push("Incidents unavailable");
    }

    setActivities(
      createActivityItems(
        deployments,
        incidents,
      ).slice(0, limit),
    );

    setError(
      errors.length > 0 ? errors.join(" • ") : null,
    );

    setLoading(false);
  }, [limit]);

  useEffect(() => {
    // Initial activity loading is intentionally triggered on mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadActivities();
  }, [loadActivities]);

  return (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <p className="text-sm font-medium text-indigo-400">
            Platform events
          </p>

          <h3 className="mt-1 text-lg font-semibold text-white">
            Recent activity
          </h3>

          <p className="mt-1 text-sm text-zinc-500">
            Recent deployment and incident activity across CloudForge.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void loadActivities()}
          disabled={loading}
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs font-medium text-zinc-300 transition hover:border-indigo-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
          {error}
        </div>
      )}

      {loading && activities.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500">
          Loading activity...
        </div>
      ) : activities.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500">
          No recent activity available
        </div>
      ) : (
        <div className="mt-6 space-y-3">
          {activities.map((activity) => {
            const content = (
              <div className="flex gap-4 rounded-xl border border-zinc-800 bg-zinc-950/40 p-4 transition hover:border-zinc-700">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-zinc-800 text-lg text-indigo-300">
                  {getActivityIcon(activity.type)}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-white">
                        {activity.title}
                      </p>

                      <p className="mt-1 text-xs leading-5 text-zinc-500">
                        {activity.description}
                      </p>
                    </div>

                    <span
                      className={`whitespace-nowrap text-xs font-semibold ${getStatusClass(
                        activity.status,
                      )}`}
                    >
                      {activity.status}
                    </span>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="text-xs text-zinc-600">
                      {activity.type === "deployment"
                        ? "Deployment"
                        : "Incident"}
                    </span>

                    {activity.severity && (
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${getSeverityClass(
                          activity.severity,
                        )}`}
                      >
                        {activity.severity}
                      </span>
                    )}

                    {activity.priority && (
                      <span className="rounded-full border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-[10px] font-semibold text-zinc-300">
                        {activity.priority}
                      </span>
                    )}

                    <span className="text-xs text-zinc-600">
                      {formatDate(activity.timestamp)}
                    </span>
                  </div>
                </div>
              </div>
            );

            if (activity.href) {
              return (
                <Link
                  key={activity.id}
                  href={activity.href}
                  className="block rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {content}
                </Link>
              );
            }

            return (
              <div key={activity.id}>
                {content}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
