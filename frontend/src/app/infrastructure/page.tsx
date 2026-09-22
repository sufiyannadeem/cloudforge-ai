"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  InfrastructureFormData,
  InfrastructureResource,
} from "@/types/infrastructure";

const initialForm: InfrastructureFormData = {
  project_id: "",
  name: "",
  resource_type: "aws_vpc",
  provider: "aws",
  region: "eu-west-1",
  configuration: "{}",
};

export default function InfrastructurePage() {
  const [resources, setResources] = useState<InfrastructureResource[]>([]);
  const [form, setForm] = useState<InfrastructureFormData>(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);

  const loadResources = useCallback(async () => {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        "/api/proxy/infrastructure/api/v1/resources",
        { cache: "no-store" },
      );

      if (!response.ok) {
        throw new Error("Failed to load infrastructure resources");
      }

      const result = await response.json();
      setResources(result.items ?? result.data ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
  // Load infrastructure resources when the page mounts.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  void loadResources();
}, [loadResources]);

  const updateField = (
    field: keyof InfrastructureFormData,
    value: string,
  ) => {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const createResource = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    try {
      setSaving(true);
      setError("");

      let configuration: Record<string, unknown>;

      try {
        configuration = JSON.parse(form.configuration);
      } catch {
        throw new Error("Configuration must contain valid JSON");
      }

      const response = await fetch(
        "/api/proxy/infrastructure/api/v1/resources",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            project_id: form.project_id,
            name: form.name,
            resource_type: form.resource_type,
            provider: form.provider,
            region: form.region,
            configuration,
          }),
        },
      );

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Failed to create resource");
      }

      setForm(initialForm);
      setShowForm(false);
      await loadResources();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setSaving(false);
    }
  };

  const deleteResource = async (id: string) => {
    if (!window.confirm("Delete this infrastructure resource?")) {
      return;
    }

    try {
      setError("");

      const response = await fetch(
        `/api/proxy/infrastructure/api/v1/resources/${id}`,
        {
          method: "DELETE",
        },
      );

      if (!response.ok) {
        throw new Error("Failed to delete infrastructure resource");
      }

      await loadResources();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-10 text-white">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Infrastructure</h1>
            <p className="mt-2 text-slate-400">
              Manage cloud infrastructure resources.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setShowForm((current) => !current)}
            className="rounded-lg bg-blue-600 px-4 py-2 font-medium hover:bg-blue-500"
          >
            {showForm ? "Cancel" : "Create Resource"}
          </button>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-red-300">
            {error}
          </div>
        )}

        {showForm && (
          <form
            onSubmit={createResource}
            className="mb-8 rounded-xl border border-slate-800 bg-slate-900 p-6"
          >
            <h2 className="mb-5 text-xl font-semibold">
              Create Infrastructure Resource
            </h2>

            <div className="grid gap-4 md:grid-cols-2">
              <input
                required
                placeholder="Project ID"
                value={form.project_id}
                onChange={(event) =>
                  updateField("project_id", event.target.value)
                }
                className="rounded-lg border border-slate-700 bg-slate-950 p-3"
              />

              <input
                required
                placeholder="Resource name"
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-950 p-3"
              />

              <select
                value={form.resource_type}
                onChange={(event) =>
                  updateField("resource_type", event.target.value)
                }
                className="rounded-lg border border-slate-700 bg-slate-950 p-3"
              >
                <option value="aws_vpc">AWS VPC</option>
                <option value="aws_eks">AWS EKS</option>
                <option value="aws_rds">AWS RDS</option>
                <option value="aws_ec2">AWS EC2</option>
                <option value="kubernetes_cluster">
                  Kubernetes Cluster
                </option>
              </select>

              <input
                required
                placeholder="Provider"
                value={form.provider}
                onChange={(event) =>
                  updateField("provider", event.target.value)
                }
                className="rounded-lg border border-slate-700 bg-slate-950 p-3"
              />

              <input
                required
                placeholder="Region"
                value={form.region}
                onChange={(event) => updateField("region", event.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-950 p-3"
              />
            </div>

            <textarea
              required
              rows={6}
              value={form.configuration}
              onChange={(event) =>
                updateField("configuration", event.target.value)
              }
              className="mt-4 w-full rounded-lg border border-slate-700 bg-slate-950 p-3 font-mono"
              placeholder='{"instance_type":"t3.micro"}'
            />

            <button
              type="submit"
              disabled={saving}
              className="mt-4 rounded-lg bg-emerald-600 px-5 py-2 font-medium hover:bg-emerald-500 disabled:opacity-50"
            >
              {saving ? "Creating..." : "Create Resource"}
            </button>
          </form>
        )}

        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
          {loading ? (
            <p className="p-6 text-slate-400">Loading resources...</p>
          ) : resources.length === 0 ? (
            <p className="p-6 text-slate-400">
              No infrastructure resources found.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="border-b border-slate-800 bg-slate-950">
                  <tr>
                    <th className="p-4">Name</th>
                    <th className="p-4">Environment</th>
                    <th className="p-4">Provider</th>
                    <th className="p-4">Region</th>
                    <th className="p-4">Status</th>
                    <th className="p-4">Actions</th>
                  </tr>
                </thead>

                <tbody>
                  {resources.map((resource) => (
                    <tr
                      key={resource.id}
                      className="border-b border-slate-800"
                    >
                      <td className="p-4 font-medium">{resource.name}</td>
                      <td className="p-4 text-slate-300">
                        {resource.environment}
                      </td>
                      <td className="p-4 text-slate-300">
                        {resource.provider}
                      </td>
                      <td className="p-4 text-slate-300">
                        {resource.region}
                      </td>
                      <td className="p-4">
                        <span className="rounded-full bg-blue-500/20 px-3 py-1 text-sm text-blue-300">
                          {resource.status}
                        </span>
                      </td>
                      <td className="p-4">
                        <button
                          type="button"
                          onClick={() => deleteResource(resource.id)}
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
      </div>
    </main>
  );
}
