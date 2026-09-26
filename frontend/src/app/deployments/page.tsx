"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import {
  Deployment,
  DeploymentAttempt,
} from "@/types/deployments";

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
  image: "",
  git_commit_sha: "",
  namespace: "cloudforge-dev",
};

export default function DeploymentsPage() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [attempts, setAttempts] = useState<
    Record<string, DeploymentAttempt[]>
  >({});
  const [form, setForm] = useState<DeploymentForm>(initialForm);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [runningId, setRunningId] = useState("");
  const [error, setError] = useState("");

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

  useEffect(() => {
    // Load deployments when the page mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadDeployments();
  }, [loadDeployments]);

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

    try {
      setSaving(true);
      setError("");

      const response = await fetch(
        "/api/proxy/deployment/api/v1/deployments",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
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
        },
      );

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Failed to run deployment");
      }

      await loadDeployments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setRunningId("");
    }
  };

  const loadAttempts = async (id: string) => {
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    }
  };

  const deleteDeployment = async (id: string) => {
    if (!window.confirm("Delete this deployment?")) {
      return;
    }

    try {
      setError("");

      const response = await fetch(
        `/api/proxy/deployment/api/v1/deployments/${id}`,
        {
          method: "DELETE",
        },
      );

      if (!response.ok) {
        throw new Error("Failed to delete deployment");
      }

      await loadDeployments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    }
  };

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-[1600px] space-y-8 p-4 sm:p-6 lg:p-8">
      <div className="mx-auto w-full max-w-[1600px]">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-[var(--cf-text)]">Deployments</h1>
            <p className="mt-2 text-[var(--cf-text-secondary)]">
              Create, execute, and monitor application deployments.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setShowForm((current) => !current)}
            className="
              rounded-lg bg-indigo-600 px-4 py-2.5
              font-semibold text-[var(--cf-text)] shadow-sm
              transition hover:bg-indigo-500
              focus:outline-none focus:ring-2
              focus:ring-indigo-500/30
            "
          >
            {showForm ? "Cancel" : "Create Deployment"}
          </button>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {showForm && (
          <form
            onSubmit={createDeployment}
            className="mb-8 rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-sm"
          >
            <h2 className="mb-5 text-xl font-semibold text-[var(--cf-text)]">
              Create Deployment
            </h2>

            <div className="grid gap-4 md:grid-cols-2">
              <input
                required
                placeholder="Project UUID"
                value={form.project_id}
                onChange={(event) =>
                  updateField("project_id", event.target.value)
                }
                className="
                  rounded-lg border border-[var(--cf-border)]
                  bg-[var(--cf-surface)]
                  p-3 text-[var(--cf-text)]
                  placeholder:text-[var(--cf-text-muted)]
                  outline-none transition
                  focus:border-indigo-500
                  focus:ring-2 focus:ring-indigo-500/20
                "
              />

              <select
                value={form.environment}
                onChange={(event) =>
                  updateField("environment", event.target.value)
                }
                className="
                  rounded-lg border border-[var(--cf-border)]
                  bg-[var(--cf-surface)]
                  p-3 text-[var(--cf-text)]
                  placeholder:text-[var(--cf-text-muted)]
                  outline-none transition
                  focus:border-indigo-500
                  focus:ring-2 focus:ring-indigo-500/20
                "
              >
                <option value="development">Development</option>
                <option value="staging">Staging</option>
                <option value="production">Production</option>
              </select>

              <input
                required
                placeholder="Container image"
                value={form.image}
                onChange={(event) =>
                  updateField("image", event.target.value)
                }
                className="
                  rounded-lg border border-[var(--cf-border)]
                  bg-[var(--cf-surface)]
                  p-3 text-[var(--cf-text)]
                  placeholder:text-[var(--cf-text-muted)]
                  outline-none transition
                  focus:border-indigo-500
                  focus:ring-2 focus:ring-indigo-500/20
                "
              />

              <input
                required
                placeholder="Git commit SHA"
                value={form.git_commit_sha}
                onChange={(event) =>
                  updateField("git_commit_sha", event.target.value)
                }
                className="
                  rounded-lg border border-[var(--cf-border)]
                  bg-[var(--cf-surface)]
                  p-3 text-[var(--cf-text)]
                  placeholder:text-[var(--cf-text-muted)]
                  outline-none transition
                  focus:border-indigo-500
                  focus:ring-2 focus:ring-indigo-500/20
                "
              />

              <input
                required
                placeholder="Kubernetes namespace"
                value={form.namespace}
                onChange={(event) =>
                  updateField("namespace", event.target.value)
                }
                className="
                  rounded-lg border border-[var(--cf-border)]
                  bg-[var(--cf-surface)]
                  p-3 text-[var(--cf-text)]
                  placeholder:text-[var(--cf-text-muted)]
                  outline-none transition
                  focus:border-indigo-500
                  focus:ring-2 focus:ring-indigo-500/20
                "
              />
            </div>

            <button
              type="submit"
              disabled={saving}
              className="
                mt-5 rounded-lg bg-indigo-600 px-5 py-2.5
                font-semibold text-[var(--cf-text)]
                transition hover:bg-indigo-500
                disabled:cursor-not-allowed disabled:opacity-50
              "
            >
              {saving ? "Creating..." : "Create Deployment"}
            </button>
          </form>
        )}

        <div className="overflow-hidden rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] shadow-sm">
          {loading ? (
            <p className="p-6 text-[var(--cf-text-secondary)]">
              Loading deployments...
            </p>
          ) : deployments.length === 0 ? (
            <p className="p-6 text-[var(--cf-text-secondary)]">
              No deployments found.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="border-b border-[var(--cf-border)] bg-[var(--cf-surface-2)]">
                  <tr>
                    <th className="p-4 text-left text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">Environment</th>
                    <th className="p-4 text-left text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">Image</th>
                    <th className="p-4 text-left text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">Namespace</th>
                    <th className="p-4 text-left text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">Status</th>
                    <th className="p-4 text-left text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-secondary)]">Actions</th>
                  </tr>
                </thead>

                <tbody>
                  {deployments.map((deployment) => (
                    <tr
                      key={deployment.id}
                      className="border-b border-[var(--cf-border)] transition-colors hover:bg-[var(--cf-surface-2)]"
                    >
                      <td className="p-4">
                        {deployment.environment}
                      </td>

                      <td className="max-w-xs truncate p-4 text-sm text-[var(--cf-text-secondary)]">
                        {deployment.image}
                      </td>

                      <td className="p-4 text-sm text-[var(--cf-text-secondary)]">
                        {deployment.namespace}
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

                      <td className="space-x-3 p-4 whitespace-nowrap">
                        <button
                          type="button"
                          disabled={runningId === deployment.id}
                          onClick={() => runDeployment(deployment.id)}
                          className="font-medium text-emerald-600 transition hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300 disabled:opacity-50"
                        >
                          {runningId === deployment.id
                            ? "Running..."
                            : "Run"}
                        </button>

                        <button
                          type="button"
                          onClick={() => loadAttempts(deployment.id)}
                          className="font-medium text-indigo-600 transition hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
                        >
                          Attempts
                        </button>

                        <button
                          type="button"
                          onClick={() => deleteDeployment(deployment.id)}
                          className="font-medium text-red-600 transition hover:text-red-500 dark:text-red-400 dark:hover:text-red-300"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {Object.entries(attempts).map(([deploymentId, records]) => (
          <div
            key={deploymentId}
            className="mt-6 rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-sm"
          >
            <h2 className="mb-4 text-xl font-semibold text-[var(--cf-text)]">
              Deployment Attempts
            </h2>

            {records.length === 0 ? (
              <p className="text-[var(--cf-text-secondary)]">No attempts found.</p>
            ) : (
              <div className="space-y-3">
                {records.map((attempt) => (
                  <div
                    key={attempt.id}
                    className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4"
                  >
                    <div className="flex justify-between">
                      <span>
                        Attempt #{attempt.attempt_number}
                      </span>

                      <span className="font-medium text-indigo-600 dark:text-indigo-400">
                        {attempt.status}
                      </span>
                    </div>

                    {attempt.error_message && (
                      <p className="mt-2 text-red-600 dark:text-red-400">
                        {attempt.error_message}
                      </p>
                    )}

                    {attempt.duration_ms !== null &&
                      attempt.duration_ms !== undefined && (
                        <p className="mt-2 text-sm text-[var(--cf-text-muted)]">
                          Duration: {attempt.duration_ms} ms
                        </p>
                      )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      </div>
    </AppShell>
  );
}
