"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
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
    <main className="min-h-screen bg-slate-950 px-6 py-10 text-white">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Deployments</h1>
            <p className="mt-2 text-slate-400">
              Create, execute, and monitor application deployments.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setShowForm((current) => !current)}
            className="rounded-lg bg-blue-600 px-4 py-2 font-medium hover:bg-blue-500"
          >
            {showForm ? "Cancel" : "Create Deployment"}
          </button>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-red-300">
            {error}
          </div>
        )}

        {showForm && (
          <form
            onSubmit={createDeployment}
            className="mb-8 rounded-xl border border-slate-800 bg-slate-900 p-6"
          >
            <h2 className="mb-5 text-xl font-semibold">
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
                className="rounded-lg border border-slate-700 bg-slate-950 p-3"
              />

              <select
                value={form.environment}
                onChange={(event) =>
                  updateField("environment", event.target.value)
                }
                className="rounded-lg border border-slate-700 bg-slate-950 p-3"
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
                className="rounded-lg border border-slate-700 bg-slate-950 p-3"
              />

              <input
                required
                placeholder="Git commit SHA"
                value={form.git_commit_sha}
                onChange={(event) =>
                  updateField("git_commit_sha", event.target.value)
                }
                className="rounded-lg border border-slate-700 bg-slate-950 p-3"
              />

              <input
                required
                placeholder="Kubernetes namespace"
                value={form.namespace}
                onChange={(event) =>
                  updateField("namespace", event.target.value)
                }
                className="rounded-lg border border-slate-700 bg-slate-950 p-3"
              />
            </div>

            <button
              type="submit"
              disabled={saving}
              className="mt-5 rounded-lg bg-emerald-600 px-5 py-2 font-medium hover:bg-emerald-500 disabled:opacity-50"
            >
              {saving ? "Creating..." : "Create Deployment"}
            </button>
          </form>
        )}

        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
          {loading ? (
            <p className="p-6 text-slate-400">
              Loading deployments...
            </p>
          ) : deployments.length === 0 ? (
            <p className="p-6 text-slate-400">
              No deployments found.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="border-b border-slate-800 bg-slate-950">
                  <tr>
                    <th className="p-4">Environment</th>
                    <th className="p-4">Image</th>
                    <th className="p-4">Namespace</th>
                    <th className="p-4">Status</th>
                    <th className="p-4">Actions</th>
                  </tr>
                </thead>

                <tbody>
                  {deployments.map((deployment) => (
                    <tr
                      key={deployment.id}
                      className="border-b border-slate-800"
                    >
                      <td className="p-4">
                        {deployment.environment}
                      </td>

                      <td className="max-w-xs truncate p-4 text-slate-300">
                        {deployment.image}
                      </td>

                      <td className="p-4 text-slate-300">
                        {deployment.namespace}
                      </td>

                      <td className="p-4">
                        <span className="rounded-full bg-blue-500/20 px-3 py-1 text-sm text-blue-300">
                          {deployment.status}
                        </span>
                      </td>

                      <td className="space-x-3 p-4 whitespace-nowrap">
                        <button
                          type="button"
                          disabled={runningId === deployment.id}
                          onClick={() => runDeployment(deployment.id)}
                          className="text-emerald-400 hover:text-emerald-300 disabled:opacity-50"
                        >
                          {runningId === deployment.id
                            ? "Running..."
                            : "Run"}
                        </button>

                        <button
                          type="button"
                          onClick={() => loadAttempts(deployment.id)}
                          className="text-blue-400 hover:text-blue-300"
                        >
                          Attempts
                        </button>

                        <button
                          type="button"
                          onClick={() => deleteDeployment(deployment.id)}
                          className="text-red-400 hover:text-red-300"
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
            className="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-6"
          >
            <h2 className="mb-4 text-xl font-semibold">
              Deployment Attempts
            </h2>

            {records.length === 0 ? (
              <p className="text-slate-400">No attempts found.</p>
            ) : (
              <div className="space-y-3">
                {records.map((attempt) => (
                  <div
                    key={attempt.id}
                    className="rounded-lg border border-slate-700 p-4"
                  >
                    <div className="flex justify-between">
                      <span>
                        Attempt #{attempt.attempt_number}
                      </span>

                      <span className="text-blue-300">
                        {attempt.status}
                      </span>
                    </div>

                    {attempt.error_message && (
                      <p className="mt-2 text-red-300">
                        {attempt.error_message}
                      </p>
                    )}

                    {attempt.duration_ms !== null &&
                      attempt.duration_ms !== undefined && (
                        <p className="mt-2 text-sm text-slate-400">
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
    </main>
  );
}
