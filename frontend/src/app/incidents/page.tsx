"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import AppShell from "@/components/layout/AppShell";
import Link from "next/link";
import {
  getIncidentStats,
  getIncidents,
} from "@/lib/incidents-api";
import type {
  Incident,
  IncidentStats,
} from "@/types/incidents";

type FilterValue = "all" | string;

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function getSeverityClass(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical":
      return "bg-rose-500/10 text-rose-700 dark:text-rose-300";

    case "warning":
      return "bg-amber-500/10 text-amber-700 dark:text-amber-300";

    case "high":
      return "bg-orange-500/10 text-orange-700 dark:text-orange-300";

    case "medium":
      return "bg-blue-500/10 text-blue-700 dark:text-blue-300";

    default:
      return "bg-[var(--cf-surface-3)] text-[var(--cf-text-secondary)]";
  }
}

function getPriorityClass(priority: string): string {
  switch (priority.toUpperCase()) {
    case "P1":
      return "bg-rose-500/10 text-rose-700 dark:text-rose-300";

    case "P2":
      return "bg-orange-500/10 text-orange-700 dark:text-orange-300";

    case "P3":
      return "bg-amber-500/10 text-amber-700 dark:text-amber-300";

    case "P4":
      return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";

    default:
      return "bg-[var(--cf-surface-3)] text-[var(--cf-text-secondary)]";
  }
}

function getStatusClass(status: string): string {
  switch (status.toLowerCase()) {
    case "resolved":
      return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";

    case "acknowledged":
      return "bg-blue-500/10 text-blue-700 dark:text-blue-300";

    case "assigned":
      return "bg-purple-500/10 text-purple-700 dark:text-purple-300";

    case "open":
      return "bg-rose-500/10 text-rose-700 dark:text-rose-300";

    default:
      return "bg-[var(--cf-surface-3)] text-[var(--cf-text-secondary)]";
  }
}

function StatCard({
  label,
  value,
  description,
}: {
  label: string;
  value: string | number;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
      <p className="text-sm font-medium text-[var(--cf-text-muted)]">
        {label}
      </p>

      <p className="mt-2 text-3xl font-bold text-[var(--cf-text)]">
        {value}
      </p>

      <p className="mt-1 text-xs text-[var(--cf-text-muted)]">
        {description}
      </p>
    </div>
  );
}

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [stats, setStats] = useState<IncidentStats | null>(null);

  const [statusFilter, setStatusFilter] =
    useState<FilterValue>("all");

  const [priorityFilter, setPriorityFilter] =
    useState<FilterValue>("all");

  const [severityFilter, setSeverityFilter] =
    useState<FilterValue>("all");

  const [serviceFilter, setServiceFilter] =
    useState<FilterValue>("all");

  const [searchQuery, setSearchQuery] = useState("");

  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadIncidents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const result = await getIncidents();
      setIncidents(result.incidents);
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : "Failed to load incidents.";

      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      setStatsLoading(true);

      const result = await getIncidentStats();
      setStats(result);
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : "Failed to load incident statistics.";

      setError(message);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Load incident data when the page mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadIncidents();

    // Load incident statistics when the page mounts.
    void loadStats();
  }, [loadIncidents, loadStats]);

   

  const services = useMemo(() => {
    return Array.from(
      new Set(
        incidents
          .map((incident) => incident.service)
          .filter(Boolean),
      ),
    ).sort((a, b) => a.localeCompare(b));
  }, [incidents]);

  const filteredIncidents = useMemo(() => {
    const normalizedSearch = searchQuery.trim().toLowerCase();

    return incidents.filter((incident) => {
      const matchesStatus =
        statusFilter === "all" ||
        incident.status.toLowerCase() ===
          statusFilter.toLowerCase();

      const matchesPriority =
        priorityFilter === "all" ||
        incident.priority.toUpperCase() ===
          priorityFilter.toUpperCase();

      const matchesSeverity =
        severityFilter === "all" ||
        incident.severity.toLowerCase() ===
          severityFilter.toLowerCase();

      const matchesService =
        serviceFilter === "all" ||
        incident.service === serviceFilter;

      const searchableText = [
        incident.id,
        incident.alert_name,
        incident.service,
        incident.summary,
        incident.probable_cause,
        incident.priority,
        incident.severity,
        incident.status,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      const matchesSearch =
        normalizedSearch.length === 0 ||
        searchableText.includes(normalizedSearch);

      return (
        matchesStatus &&
        matchesPriority &&
        matchesSeverity &&
        matchesService &&
        matchesSearch
      );
    });
  }, [
    incidents,
    priorityFilter,
    searchQuery,
    serviceFilter,
    severityFilter,
    statusFilter,
  ]);

  const resetFilters = () => {
    setStatusFilter("all");
    setPriorityFilter("all");
    setSeverityFilter("all");
    setServiceFilter("all");
    setSearchQuery("");
  };

  return (
    <AppShell>
      <main className="min-w-0 space-y-6 bg-[var(--cf-background)] p-4 text-[var(--cf-text)] md:p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div>
            <p className="text-sm font-medium text-blue-600">
              AIOps / Incident Intelligence
            </p>

            <h1 className="mt-1 text-3xl font-bold text-white">
	
              Incidents
            </h1>

            <p className="mt-2 text-sm text-[var(--cf-text-muted)]">
              Monitor, investigate, and track operational incidents.
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              void loadIncidents();
              void loadStats();
            }}
            className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-4 py-2 text-sm font-medium text-[var(--cf-text)] transition hover:bg-[var(--cf-surface-2)] disabled:cursor-not-allowed disabled:opacity-50"          >
            Refresh
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Total Incidents"
            value={
              statsLoading
                ? "..."
                : stats?.total_incidents ?? 0
            }
            description="All stored incidents"
          />

          <StatCard
            label="Open Incidents"
            value={
              statsLoading
                ? "..."
                : stats?.open_incidents ?? 0
            }
            description="Incidents requiring attention"
          />

          <StatCard
            label="Resolved Incidents"
            value={
              statsLoading
                ? "..."
                : stats?.resolved_incidents ?? 0
            }
            description="Successfully resolved incidents"
          />

          <StatCard
            label="Total Alerts"
            value={
              statsLoading
                ? "..."
                : stats?.total_alerts ?? 0
            }
            description="Alerts grouped into incidents"
          />
        </section>

        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
          <div className="mb-4 flex flex-col justify-between gap-3 md:flex-row md:items-center">
            <div>
              <h2 className="text-lg font-semibold text-[var(--cf-text)]">
                Incident Filters
              </h2>

              <p className="text-sm text-[var(--cf-text-muted)]">
                Narrow the incident list by operational attributes.
              </p>
            </div>

            <button
              type="button"
              onClick={resetFilters}
              className="text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              Clear filters
            </button>
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            <div>
              <label
                htmlFor="incident-search"
                className="mb-1 block text-sm font-medium text-[var(--cf-text-secondary)]"
              >
                Search
              </label>

              <input
                id="incident-search"
                type="search"
                value={searchQuery}
                onChange={(event) =>
                  setSearchQuery(event.target.value)
                }
                placeholder="Search incidents..."
                className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-3 py-2 text-sm text-[var(--cf-text)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
              />
            </div>

            <div>
              <label
                htmlFor="status-filter"
                className="mb-1 block text-sm font-medium text-[var(--cf-text-secondary)]"
              >
                Status
              </label>

              <select
                id="status-filter"
                value={statusFilter}
                onChange={(event) =>
                  setStatusFilter(event.target.value)
                }
                className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-3 py-2 text-sm text-[var(--cf-text)]"
              >
                <option value="all">All statuses</option>
                <option value="open">Open</option>
                <option value="acknowledged">
                  Acknowledged
                </option>
                <option value="assigned">Assigned</option>
                <option value="resolved">Resolved</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="priority-filter"
                className="mb-1 block text-sm font-medium text-[var(--cf-text-secondary)]"
              >
                Priority
              </label>

              <select
                id="priority-filter"
                value={priorityFilter}
                onChange={(event) =>
                  setPriorityFilter(event.target.value)
                }
                className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-3 py-2 text-sm text-[var(--cf-text)]"
              >
                <option value="all">All priorities</option>
                <option value="P1">P1</option>
                <option value="P2">P2</option>
                <option value="P3">P3</option>
                <option value="P4">P4</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="severity-filter"
                className="mb-1 block text-sm font-medium text-[var(--cf-text-secondary)]"
              >
                Severity
              </label>

              <select
                id="severity-filter"
                value={severityFilter}
                onChange={(event) =>
                  setSeverityFilter(event.target.value)
                }
                className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-3 py-2 text-sm text-[var(--cf-text)]"
              >
                <option value="all">All severities</option>
                <option value="critical">Critical</option>
                <option value="warning">Warning</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="service-filter"
                className="mb-1 block text-sm font-medium text-[var(--cf-text-secondary)]"
              >
                Service
              </label>

              <select
                id="service-filter"
                value={serviceFilter}
                onChange={(event) =>
                  setServiceFilter(event.target.value)
                }
                className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-3 py-2 text-sm text-[var(--cf-text)]"
              >
                <option value="all">All services</option>

                {services.map((service) => (
                  <option key={service} value={service}>
                    {service}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

        <section className="overflow-hidden rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] shadow-sm">
          <div className="flex flex-col justify-between gap-2 border-b border-[var(--cf-border)] p-5 md:flex-row md:items-center">
            <div>
              <h2 className="text-lg font-semibold text-[var(--cf-text)]">
                Incident List
              </h2>

              <p className="text-sm text-[var(--cf-text-muted)]">
                Showing {filteredIncidents.length} of{" "}
                {incidents.length} incidents
              </p>
            </div>
          </div>

          {loading ? (
            <div className="p-8 text-center text-sm text-[var(--cf-text-muted)]">
              Loading incidents...
            </div>
          ) : filteredIncidents.length === 0 ? (
            <div className="p-8 text-center text-sm text-[var(--cf-text-muted)]">
              No incidents match the selected filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-[var(--cf-border)]">
                <thead className="bg-[var(--cf-surface-2)]">
                  <tr>
                    <th className="whitespace-nowrap px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-muted)]">
                      Incident
                    </th>

                    <th className="whitespace-nowrap px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-muted)]">
                      Service
                    </th>

                    <th className="whitespace-nowrap px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-muted)]">
                      Severity
                    </th>

                    <th className="whitespace-nowrap px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-muted)]">
                      Priority
                    </th>

                    <th className="whitespace-nowrap px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-muted)]">
                      Status
                    </th>

                    <th className="whitespace-nowrap px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-muted)]">
                      Alerts
                    </th>

                    <th className="whitespace-nowrap px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-muted)]">
                      Updated
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-[var(--cf-border)]">
                  {filteredIncidents.map((incident) => (
                    <tr
                      key={incident.id}
                      className="transition hover:bg-[var(--cf-surface-2)]"
                    >
                      <td className="max-w-md px-5 py-4">
                        <Link
			  href={`/incidents/${incident.id}`}
                          className="font-medium text-blue-600 transition hover:text-blue-700 hover:underline"
			 >
  			  {incident.alert_name}
			 </Link>

                        <p className="mt-1 text-xs text-[var(--cf-text-muted)]">
                          {incident.id}
                        </p>

                        <p className="mt-2 text-sm text-[var(--cf-text-secondary)]">
                          {incident.summary}
                        </p>
                      </td>

                      <td className="whitespace-nowrap px-5 py-4 text-sm text-[var(--cf-text-secondary)]">
                        {incident.service}
                      </td>

                      <td className="whitespace-nowrap px-5 py-4">
                        <span
                          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${getSeverityClass(
                            incident.severity,
                          )}`}
                        >
                          {incident.severity}
                        </span>
                      </td>

                      <td className="whitespace-nowrap px-5 py-4">
                        <span
                          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${getPriorityClass(
                            incident.priority,
                          )}`}
                        >
                          {incident.priority}
                        </span>
                      </td>

                      <td className="whitespace-nowrap px-5 py-4">
                        <span
                          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${getStatusClass(
                            incident.status,
                          )}`}
                        >
                          {incident.status}
                        </span>
                      </td>

                      <td className="whitespace-nowrap px-5 py-4 text-sm text-[var(--cf-text-secondary)]">
                        {incident.alert_count}
                      </td>

                      <td className="whitespace-nowrap px-5 py-4 text-sm text-[var(--cf-text-muted)]">
                        {formatDate(incident.updated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </AppShell>
  );
}
