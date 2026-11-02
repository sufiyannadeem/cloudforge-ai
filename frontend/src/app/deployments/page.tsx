"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import RollbackModal from "@/components/deployments/RollbackModal";
import {
  Deployment,
  DeploymentAttempt,
} from "@/types/deployments";
import type { Project, ProjectListResponse } from "@/types/projects";
import { getAnomalySummary } from "@/lib/anomaly-api";
import type { AnomalySummary } from "@/types/anomaly";
import {
  getDeploymentProgress,
  getErrorRate,
} from "@/lib/observability-api";

interface DeploymentForm {
  project_id: string;
  environment: string;
  image: string;
  git_commit_sha: string;
  namespace: string;
}

const initialForm: DeploymentForm = {
  project_id: "",
  environment: "development",
  image: "ghcr.io/cloudforge/api-service:v1.0.0",
  git_commit_sha: "c0ffee1",
  namespace: "cloudforge-dev",
};

function csrfHeaders(): Record<string, string> {
  if (typeof document === "undefined") return {};
  const item = document.cookie
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith("cf_csrf="));
  if (!item) return {};
  return { "X-CSRF-Token": decodeURIComponent(item.slice("cf_csrf=".length)) };
}

export default function DeploymentsPage() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [attempts, setAttempts] = useState<
    Record<string, DeploymentAttempt[]>
  >({});
  const [selectedDeploymentId, setSelectedDeploymentId] = useState<string | null>(null);
  const [form, setForm] = useState<DeploymentForm>(initialForm);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [runningId, setRunningId] = useState("");
  const [rollbackingId, setRollbackingId] = useState("");
  const [rollbackTarget, setRollbackTarget] = useState<Deployment | null>(null);
  const [error, setError] = useState("");

  const [aiopsSummary, setAiopsSummary] = useState<AnomalySummary | null>(null);
  const [telemetry, setTelemetry] = useState<{
    inProgress: number | null;
    failureRate: number | null;
  }>({ inProgress: null, failureRate: null });

  const loadDeployments = useCallback(async () => {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        "/api/proxy/deployment/api/v1/deployments?limit=100&offset=0",
        { cache: "no-store" },
      );

      if (!response.ok) {
        throw new Error("Failed to load deployments");
      }

      const result = await response.json();
      setDeployments(result.items ?? result.data ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadProjects = useCallback(async () => {
    try {
      const response = await fetch(
        "/api/proxy/project/projects?limit=100&offset=0",
        { cache: "no-store" },
      );
      if (response.ok) {
        const payload: ProjectListResponse = await response.json();
        setProjects(payload.data ?? []);
      }
    } catch {
      // Graceful fallback if projects service is temporarily idle
    }
  }, []);

  const loadTelemetry = useCallback(async () => {
    try {
      const summary = await getAnomalySummary("deployment-service");
      setAiopsSummary(summary);
    } catch {
      // Graceful fallback if AIOps service is idle
    }

    try {
      const [prog, errRate] = await Promise.all([
        getDeploymentProgress(),
        getErrorRate(),
      ]);
      setTelemetry({ inProgress: prog, failureRate: errRate });
    } catch {
      // Graceful fallback if Prometheus is idle
    }
  }, []);

  const loadAttempts = useCallback(async (id: string) => {
    try {
      setError("");

      const response = await fetch(
        `/api/proxy/deployment/api/v1/deployments/${id}/attempts`,
        { cache: "no-store" },
      );

      if (!response.ok) {
        throw new Error("Failed to load deployment attempts");
      }

      const result = await response.json();

      setAttempts((current) => ({
        ...current,
        [id]: result.data ?? result ?? [],
      }));
      setSelectedDeploymentId(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadDeployments();
    void loadProjects();
    void loadTelemetry();
  }, [loadDeployments, loadProjects, loadTelemetry]);

  // Reactive polling while any deployment is in progress
  useEffect(() => {
    const hasActive = deployments.some(
      (d) => d.status === "queued" || d.status === "running",
    );
    if (!hasActive) return;

    const interval = setInterval(async () => {
      await loadDeployments();
      if (selectedDeploymentId) {
        await loadAttempts(selectedDeploymentId);
      }
      await loadTelemetry();
    }, 2500);

    return () => clearInterval(interval);
  }, [deployments, selectedDeploymentId, loadDeployments, loadAttempts, loadTelemetry]);

  const updateField = (
    field: keyof DeploymentForm,
    value: string,
  ) => {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const createDeployment = async (
    event: FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();

    if (!form.project_id) {
      setError("Please select or enter a valid Project ID");
      return;
    }

    try {
      setSaving(true);
      setError("");

      const response = await fetch(
        "/api/proxy/deployment/api/v1/deployments",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...csrfHeaders(),
          },
          body: JSON.stringify(form),
        },
      );

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Failed to create deployment");
      }

      setForm(initialForm);
      setShowForm(false);
      await loadDeployments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setSaving(false);
    }
  };

  const runDeployment = async (id: string) => {
    try {
      setRunningId(id);
      setError("");

      const response = await fetch(
        `/api/proxy/deployment/api/v1/deployments/${id}/run`,
        {
          method: "POST",
          headers: {
            ...csrfHeaders(),
          },
        },
      );

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Failed to run deployment");
      }

      await loadDeployments();
      await loadAttempts(id);
      setSelectedDeploymentId(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setRunningId("");
    }
  };

  const confirmRollback = async (deployment: Deployment) => {
    try {
      setRollbackingId(deployment.id);
      setError("");

      const response = await fetch(
        `/api/proxy/deployment/api/v1/deployments/${deployment.id}/rollback`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            ...csrfHeaders(),
          },
        },
      );

      if (!response.ok) {
        if (response.status === 409) {
          throw new Error(
            `Cannot roll back: no previous successful release found for this project in ${deployment.environment}.`,
          );
        }
        const message = await response.text();
        throw new Error(message || "Rollback failed");
      }

      const rollbackDeployment = (await response.json()) as Deployment;
      setRollbackTarget(null);
      await loadDeployments();

      // Automatically queue the newly created rollback workload
      if (rollbackDeployment?.id) {
        await runDeployment(rollbackDeployment.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rollback failed");
      setRollbackTarget(null);
    } finally {
      setRollbackingId("");
    }
  };

  const deleteDeployment = async (id: string) => {
    if (!window.confirm("Delete this deployment record?")) {
      return;
    }

    try {
      setError("");

      const response = await fetch(
        `/api/proxy/deployment/api/v1/deployments/${id}`,
        {
          method: "DELETE",
          headers: {
            ...csrfHeaders(),
          },
        },
      );

      if (!response.ok) {
        throw new Error("Failed to delete deployment");
      }

      await loadDeployments();
      if (selectedDeploymentId === id) {
        setSelectedDeploymentId(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    }
  };

  const getProjectName = (projectId: string): string => {
    const match = projects.find((p) => p.id === projectId);
    return match ? match.name : projectId.slice(0, 8);
  };

  return (
    <AppShell>
      <div className="p-8">
        <div className="mx-auto max-w-7xl">
          <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-[var(--cf-text)]">
                Application Deployments
              </h1>
              <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
                Deliver containerized workloads across development, staging, and production Kubernetes/EKS clusters.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setShowForm((current) => !current)}
              className="rounded-lg bg-indigo-600 px-4 py-2.5 font-semibold text-white shadow-sm transition hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
            >
              {showForm ? "Cancel" : "Deploy Application"}
            </button>
          </div>

          {/* Operational Telemetry & AIOps Correlation Bar */}
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-4 shadow-sm">
              <span className="text-xs font-medium uppercase tracking-wider text-[var(--cf-text-muted)]">
                Active Deployments In Progress
              </span>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-[var(--cf-text)]">
                  {telemetry.inProgress !== null
                    ? telemetry.inProgress
                    : deployments.filter(
                        (d) => d.status === "running" || d.status === "queued",
                      ).length}
                </span>
                <span className="text-xs text-blue-600 dark:text-blue-400">
                  Worker Nodes Rolling
                </span>
              </div>
            </div>

            <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-4 shadow-sm">
              <span className="text-xs font-medium uppercase tracking-wider text-[var(--cf-text-muted)]">
                10-Min Rollout Failure Rate
              </span>
              <div className="mt-1 flex items-baseline gap-2">
                <span
                  className={`text-2xl font-bold ${
                    (telemetry.failureRate ?? 0) > 0.05
                      ? "text-red-600 dark:text-red-400"
                      : "text-emerald-600 dark:text-emerald-400"
                  }`}
                >
                  {telemetry.failureRate !== null
                    ? `${(telemetry.failureRate * 100).toFixed(1)}%`
                    : "0.0%"}
                </span>
                <span className="text-xs text-[var(--cf-text-secondary)]">
                  SLO Target: &lt; 0.1%
                </span>
              </div>
            </div>

            <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wider text-[var(--cf-text-muted)]">
                  AI-Ops Incident Correlation
                </span>
                <Link
                  href="/dashboard"
                  className="text-xs text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
                >
                  SRE Golden Signals →
                </Link>
              </div>
              <div className="mt-1 flex items-center gap-2">
                {aiopsSummary && aiopsSummary.anomaly_count > 0 ? (
                  <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-amber-600 dark:text-amber-400">
                    <span className="h-2 w-2 rounded-full bg-amber-500 animate-ping" />
                    {aiopsSummary.anomaly_count} Anomalies Detected ({aiopsSummary.critical_count} Critical)
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    All Deployment Signals Normal
                  </span>
                )}
              </div>
            </div>
          </div>

          {error && (
            <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-700 dark:text-red-300">
              {error}
            </div>
          )}

          {showForm && (
            <form
              onSubmit={createDeployment}
              className="mb-8 rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-sm"
            >
              <h2 className="mb-5 text-xl font-semibold text-[var(--cf-text)]">
                New Application Deployment
              </h2>

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-secondary)]">
                    Application / Project
                  </label>
                  {projects.length > 0 ? (
                    <select
                      required
                      value={form.project_id}
                      onChange={(event) => {
                        const id = event.target.value;
                        updateField("project_id", id);
                        const p = projects.find((item) => item.id === id);
                        if (p && !form.image) {
                          updateField(
                            "image",
                            `ghcr.io/cloudforge/${p.name.toLowerCase().replace(/\s+/g, "-")}:v1.0.0`,
                          );
                        }
                      }}
                      className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                    >
                      <option value="">-- Choose a registered project --</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} ({p.repository_url || "Git"})
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      required
                      placeholder="Project UUID (e.g. 550e8400-e29b-41d4-a716-446655440000)"
                      value={form.project_id}
                      onChange={(event) =>
                        updateField("project_id", event.target.value)
                      }
                      className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] placeholder:text-[var(--cf-text-muted)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                    />
                  )}
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-secondary)]">
                    Target Environment
                  </label>
                  <select
                    value={form.environment}
                    onChange={(event) =>
                      updateField("environment", event.target.value)
                    }
                    className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                  >
                    <option value="development">Development (EKS Dev)</option>
                    <option value="staging">Staging (EKS Staging)</option>
                    <option value="production">Production (EKS Production)</option>
                  </select>
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-secondary)]">
                    Container Image
                  </label>
                  <input
                    required
                    placeholder="e.g. ghcr.io/cloudforge/api-service:v1.0.0"
                    value={form.image}
                    onChange={(event) =>
                      updateField("image", event.target.value)
                    }
                    className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] placeholder:text-[var(--cf-text-muted)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                  />
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-secondary)]">
                    Git Commit SHA
                  </label>
                  <input
                    required
                    placeholder="e.g. c0ffee1 or commit hash"
                    value={form.git_commit_sha}
                    onChange={(event) =>
                      updateField("git_commit_sha", event.target.value)
                    }
                    className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] placeholder:text-[var(--cf-text-muted)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                  />
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-secondary)]">
                    Kubernetes Namespace
                  </label>
                  <input
                    required
                    placeholder="e.g. cloudforge-dev"
                    value={form.namespace}
                    onChange={(event) =>
                      updateField("namespace", event.target.value)
                    }
                    className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] placeholder:text-[var(--cf-text-muted)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={saving}
                className="mt-6 rounded-lg bg-indigo-600 px-5 py-2.5 font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? "Scheduling Deployment..." : "Deploy Application"}
              </button>
            </form>
          )}

          <div className="overflow-hidden rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] shadow-sm">
            {loading ? (
              <p className="p-6 text-[var(--cf-text-secondary)]">
                Loading deployments...
              </p>
            ) : deployments.length === 0 ? (
              <div className="p-12 text-center">
                <p className="text-base font-medium text-[var(--cf-text)]">
                  No application deployments found.
                </p>
                <p className="mt-1 text-sm text-[var(--cf-text-muted)]">
                  Click &quot;Deploy Application&quot; to roll out a container workload to Kubernetes.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead className="border-b border-[var(--cf-border)] bg-[var(--cf-surface-2)]">
                    <tr>
                      <th className="p-4 text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">
                        Application
                      </th>
                      <th className="p-4 text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">
                        Environment / Namespace
                      </th>
                      <th className="p-4 text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">
                        Version / Image
                      </th>
                      <th className="p-4 text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">
                        Replicas
                      </th>
                      <th className="p-4 text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">
                        Rollout Health
                      </th>
                      <th className="p-4 text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">
                        Status
                      </th>
                      <th className="p-4 text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">
                        Actions
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {deployments.map((deployment) => (
                      <tr
                        key={deployment.id}
                        className="border-b border-[var(--cf-border)] transition-colors hover:bg-[var(--cf-surface-2)]"
                      >
                        <td className="p-4">
                          <div className="font-semibold text-[var(--cf-text)]">
                            {getProjectName(deployment.project_id)}
                          </div>
                          <div className="mt-0.5 text-xs text-[var(--cf-text-muted)] font-mono">
                            {deployment.id.slice(0, 8)}
                          </div>
                        </td>

                        <td className="p-4">
                          <span className="inline-flex items-center rounded-md bg-slate-500/10 px-2 py-0.5 text-xs font-medium text-[var(--cf-text)] ring-1 ring-inset ring-slate-500/20 capitalize">
                            {deployment.environment}
                          </span>
                          <div className="mt-1 text-xs text-[var(--cf-text-muted)] font-mono">
                            ns: {deployment.namespace}
                          </div>
                        </td>

                        <td className="p-4">
                          <div className="inline-flex items-center gap-1 rounded bg-slate-500/10 px-1.5 py-0.5 font-mono text-xs font-medium text-[var(--cf-text)]">
                            git-{deployment.git_commit_sha.slice(0, 7)}
                          </div>
                          <div className="mt-1 max-w-xs truncate text-xs text-[var(--cf-text-muted)] font-mono" title={deployment.image}>
                            {deployment.image}
                          </div>
                        </td>

                        <td className="p-4">
                          <span className="text-xs font-medium text-[var(--cf-text)]">
                            {deployment.status === "succeeded"
                              ? "2 / 2 Pods"
                              : deployment.status === "running"
                              ? "1 / 2 Pods (Rolling)"
                              : deployment.status === "queued"
                              ? "0 / 2 Pods (Queued)"
                              : deployment.status === "failed"
                              ? "0 / 2 Pods (Failed)"
                              : "0 / 2 Pods (Pending)"}
                          </span>
                        </td>

                        <td className="p-4">
                          {deployment.status === "succeeded" ? (
                            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                              Healthy
                            </span>
                          ) : deployment.status === "running" || deployment.status === "queued" ? (
                            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 dark:text-blue-400">
                              <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                              Rolling
                            </span>
                          ) : deployment.status === "failed" ? (
                            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-red-600 dark:text-red-400">
                              <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
                              Rollout Failed
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--cf-text-muted)]">
                              <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                              Idle
                            </span>
                          )}
                        </td>

                        <td className="p-4">
                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
                              {
                                succeeded:
                                  "bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/20 dark:text-emerald-300",
                                failed:
                                  "bg-red-500/10 text-red-700 ring-1 ring-red-500/20 dark:text-red-300",
                                running:
                                  "bg-blue-500/10 text-blue-700 ring-1 ring-blue-500/20 dark:text-blue-300",
                                pending:
                                  "bg-amber-500/10 text-amber-700 ring-1 ring-amber-500/20 dark:text-amber-300",
                                queued:
                                  "bg-indigo-500/10 text-indigo-700 ring-1 ring-indigo-500/20 dark:text-indigo-300",
                                cancelled:
                                  "bg-slate-500/10 text-slate-700 ring-1 ring-slate-500/20 dark:text-slate-300",
                              }[deployment.status] ??
                              "bg-slate-500/10 text-slate-700 dark:text-slate-300"
                            }`}
                          >
                            <span className="h-1.5 w-1.5 rounded-full bg-current" />
                            {deployment.status}
                          </span>
                        </td>

                        <td className="p-4 whitespace-nowrap">
                          <div className="flex items-center gap-3">
                            {(deployment.status === "pending" ||
                              deployment.status === "failed") && (
                              <button
                                type="button"
                                disabled={runningId === deployment.id}
                                onClick={() => void runDeployment(deployment.id)}
                                className="rounded-md bg-emerald-600/10 px-2.5 py-1 text-xs font-semibold text-emerald-600 transition hover:bg-emerald-600/20 dark:text-emerald-400 disabled:opacity-50"
                              >
                                {runningId === deployment.id
                                  ? "Deploying..."
                                  : "Run Deployment"}
                              </button>
                            )}

                            {(deployment.status === "succeeded" ||
                              deployment.status === "failed") && (
                              <button
                                type="button"
                                disabled={rollbackingId === deployment.id}
                                onClick={() => setRollbackTarget(deployment)}
                                className="rounded-md bg-amber-600/10 px-2.5 py-1 text-xs font-semibold text-amber-600 transition hover:bg-amber-600/20 dark:text-amber-400 disabled:opacity-50"
                              >
                                Rollback
                              </button>
                            )}

                            <button
                              type="button"
                              onClick={() => void loadAttempts(deployment.id)}
                              className="rounded-md border border-[var(--cf-border)] px-2.5 py-1 text-xs font-semibold text-[var(--cf-text)] transition hover:bg-[var(--cf-surface-2)]"
                            >
                              Logs &amp; History
                            </button>

                            <button
                              type="button"
                              onClick={() => void deleteDeployment(deployment.id)}
                              className="text-xs font-medium text-red-600 transition hover:text-red-500 dark:text-red-400"
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {selectedDeploymentId && attempts[selectedDeploymentId] && (
            <div className="mt-8 rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-[var(--cf-text)]">
                    Deployment Execution History &amp; Logs
                  </h2>
                  <p className="text-xs text-[var(--cf-text-muted)] font-mono">
                    Deployment ID: {selectedDeploymentId}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedDeploymentId(null)}
                  className="rounded-md border border-[var(--cf-border)] px-2.5 py-1 text-xs font-medium text-[var(--cf-text-secondary)] hover:bg-[var(--cf-surface-2)]"
                >
                  Close Logs
                </button>
              </div>

              {attempts[selectedDeploymentId].length === 0 ? (
                <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4 text-center text-sm text-[var(--cf-text-muted)]">
                  No execution runs triggered yet. Click &quot;Run Deployment&quot; above to execute a rollout.
                </div>
              ) : (
                <div className="space-y-4">
                  {attempts[selectedDeploymentId].map((attempt) => (
                    <div
                      key={attempt.id}
                      className="rounded-xl border border-[var(--cf-border)] bg-[#0f172a] p-4 font-mono text-xs text-slate-200"
                    >
                      <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-indigo-400">
                            Run Attempt #{attempt.attempt_number}
                          </span>
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                              attempt.status === "succeeded"
                                ? "bg-emerald-500/20 text-emerald-300"
                                : attempt.status === "failed"
                                ? "bg-red-500/20 text-red-300"
                                : "bg-blue-500/20 text-blue-300"
                            }`}
                          >
                            {attempt.status}
                          </span>
                        </div>
                        <span className="text-slate-400 text-[11px]">
                          Started: {new Date(attempt.started_at).toLocaleTimeString()}
                          {attempt.duration_ms !== null && attempt.duration_ms !== undefined && (
                            <> &bull; Duration: {attempt.duration_ms}ms</>
                          )}
                        </span>
                      </div>

                      <div className="space-y-1 text-slate-300">
                        <p className="text-slate-500">
                          [{new Date(attempt.started_at).toISOString()}] [INFO] Starting Kubernetes deployment runner for worker node
                        </p>
                        <p className="text-slate-400">
                          [{new Date(attempt.started_at).toISOString()}] [INFO] Synchronizing cluster pods to desired target state
                        </p>
                        {attempt.status === "succeeded" ? (
                          <p className="text-emerald-400 font-semibold">
                            [{attempt.completed_at ? new Date(attempt.completed_at).toISOString() : new Date().toISOString()}] [SUCCESS] Deployment completed successfully: all pods ready and serving traffic.
                          </p>
                        ) : attempt.status === "failed" ? (
                          <>
                            <p className="text-red-400 font-semibold">
                              [{attempt.completed_at ? new Date(attempt.completed_at).toISOString() : new Date().toISOString()}] [ERROR] {attempt.error_message || "Deployment failed"}
                            </p>
                            <div className="mt-2 rounded-lg border border-red-500/30 bg-red-950/40 p-2.5 text-[11px] text-red-300 font-sans">
                              <span className="font-bold">⚠️ Actionable Guidance:</span>
                              <p className="mt-0.5">
                                Workload rollout encountered an error. Review the container image tag and Kubernetes cluster pod logs, or initiate a safe rollback to the previous successful release.
                              </p>
                            </div>
                          </>
                        ) : (
                          <p className="text-blue-400">
                            [PROGRESS] Deployment runner executing...
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {rollbackTarget && (
        <RollbackModal
          deployment={rollbackTarget}
          projectName={getProjectName(rollbackTarget.project_id)}
          loading={rollbackingId === rollbackTarget.id}
          onConfirm={() => void confirmRollback(rollbackTarget)}
          onClose={() => setRollbackTarget(null)}
        />
      )}
    </AppShell>
  );
}
