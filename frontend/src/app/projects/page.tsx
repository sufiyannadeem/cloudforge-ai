"use client";

import { useCallback, useEffect, useState } from "react";
import type {
  CreateProjectInput,
  Project,
  ProjectListResponse,
} from "@/types/projects";

const PROJECTS_API = "/api/proxy/project/projects";

const emptyForm: CreateProjectInput = {
  name: "",
  description: "",
  repository_url: "",
  default_branch: "main",
};

async function requestJson<T>(
  url: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...options?.headers,
    },
    cache: "no-store",
  });

  const contentType =
    response.headers.get("content-type") ?? "";

  const body = contentType.includes("application/json")
    ? await response.json()
    : null;

  if (!response.ok) {
    const message =
      body?.error?.message ??
      body?.message ??
      `Request failed: ${response.status}`;

    throw new Error(message);
  }

  return body as T;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [editingProject, setEditingProject] =
    useState<Project | null>(null);

  const [form, setForm] =
    useState<CreateProjectInput>(emptyForm);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response =
        await requestJson<ProjectListResponse>(
          `${PROJECTS_API}?limit=100&offset=0`,
        );

      setProjects(response.data ?? []);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load projects",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
  // The initial data load is intentionally triggered on mount.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  void loadProjects();
}, [loadProjects]);

  const openCreateForm = () => {
    setEditingProject(null);
    setForm(emptyForm);
    setError(null);
    setShowForm(true);
  };

  const openEditForm = (project: Project) => {
    setEditingProject(project);

    setForm({
      name: project.name,
      description: project.description ?? "",
      repository_url: project.repository_url,
      default_branch: project.default_branch,
    });

    setError(null);
    setShowForm(true);
  };

  const closeForm = () => {
    if (!saving) {
      setShowForm(false);
    }
  };

  const updateField = (
    field: keyof CreateProjectInput,
    value: string,
  ) => {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const saveProject = async (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();

    if (!form.name.trim()) {
      setError("Project name is required");
      return;
    }

    if (!form.repository_url.trim()) {
      setError("Repository URL is required");
      return;
    }

    if (!form.default_branch.trim()) {
      setError("Default branch is required");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      if (editingProject) {
        await requestJson<Project>(
          `${PROJECTS_API}/${encodeURIComponent(
            editingProject.id,
          )}`,
          {
            method: "PATCH",
            body: JSON.stringify(form),
          },
        );
      } else {
        await requestJson<Project>(PROJECTS_API, {
          method: "POST",
          body: JSON.stringify(form),
        });
      }

      setShowForm(false);
      setEditingProject(null);
      setForm(emptyForm);

      await loadProjects();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to save project",
      );
    } finally {
      setSaving(false);
    }
  };

  const deleteProject = async (project: Project) => {
    const confirmed = window.confirm(
      `Delete project "${project.name}"? This action cannot be undone.`,
    );

    if (!confirmed) {
      return;
    }

    setError(null);

    try {
      await requestJson<void>(
        `${PROJECTS_API}/${encodeURIComponent(project.id)}`,
        {
          method: "DELETE",
        },
      );

      await loadProjects();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to delete project",
      );
    }
  };

  return (
    <main className="min-h-screen bg-zinc-950 px-4 py-8 text-white sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-8">
        <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="text-sm font-medium text-indigo-400">
              CloudForge Platform
            </p>

            <h1 className="mt-2 text-3xl font-bold tracking-tight">
              Projects
            </h1>

            <p className="mt-2 text-sm text-zinc-400">
              Manage repositories and project configuration.
            </p>
          </div>

          <button
            type="button"
            onClick={openCreateForm}
            className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500"
          >
            + Create project
          </button>
        </header>

        {error && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-300">
            {error}
          </div>
        )}

        <section className="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
            <div>
              <h2 className="font-semibold text-white">
                All projects
              </h2>

              <p className="mt-1 text-xs text-zinc-500">
                {projects.length} project(s) loaded
              </p>
            </div>

            <button
              type="button"
              onClick={() => void loadProjects()}
              disabled={loading}
              className="rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            >
              {loading ? "Loading..." : "Refresh"}
            </button>
          </div>

          {loading ? (
            <div className="px-5 py-16 text-center text-sm text-zinc-500">
              Loading projects...
            </div>
          ) : projects.length === 0 ? (
            <div className="px-5 py-16 text-center">
              <p className="text-sm text-zinc-400">
                No projects found.
              </p>

              <button
                type="button"
                onClick={openCreateForm}
                className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500"
              >
                Create your first project
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-zinc-900 text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="px-5 py-4">Project</th>
                    <th className="px-5 py-4">Repository</th>
                    <th className="px-5 py-4">Branch</th>
                    <th className="px-5 py-4">Status</th>
                    <th className="px-5 py-4 text-right">
                      Actions
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-zinc-800">
                  {projects.map((project) => (
                    <tr
                      key={project.id}
                      className="transition hover:bg-zinc-900"
                    >
                      <td className="px-5 py-4">
                        <p className="font-medium text-white">
                          {project.name}
                        </p>

                        <p className="mt-1 max-w-xs truncate text-xs text-zinc-500">
                          {project.description ||
                            "No description"}
                        </p>
                      </td>

                      <td className="max-w-xs px-5 py-4">
                        <a
                          href={project.repository_url}
                          target="_blank"
                          rel="noreferrer"
                          className="block truncate text-indigo-400 hover:text-indigo-300"
                        >
                          {project.repository_url}
                        </a>
                      </td>

                      <td className="px-5 py-4 font-mono text-xs text-zinc-400">
                        {project.default_branch}
                      </td>

                      <td className="px-5 py-4">
                        <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs font-medium capitalize text-emerald-400">
                          {project.status}
                        </span>
                      </td>

                      <td className="px-5 py-4">
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              openEditForm(project)
                            }
                            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
                          >
                            Edit
                          </button>

                          <button
                            type="button"
                            onClick={() =>
                              void deleteProject(project)
                            }
                            className="rounded-md border border-rose-500/30 px-3 py-1.5 text-xs text-rose-400 hover:bg-rose-500/10"
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
        </section>

        {showForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
            <div className="w-full max-w-lg rounded-2xl border border-zinc-700 bg-zinc-900 p-6 shadow-2xl">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold text-white">
                  {editingProject
                    ? "Edit project"
                    : "Create project"}
                </h2>

                <button
                  type="button"
                  onClick={closeForm}
                  disabled={saving}
                  className="text-xl text-zinc-500 hover:text-white"
                >
                  ×
                </button>
              </div>

              <form
                onSubmit={saveProject}
                className="mt-6 space-y-4"
              >
                <label className="block">
                  <span className="text-sm text-zinc-300">
                    Project name
                  </span>

                  <input
                    value={form.name}
                    onChange={(event) =>
                      updateField("name", event.target.value)
                    }
                    placeholder="CloudForge Application"
                    className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                    required
                  />
                </label>

                <label className="block">
                  <span className="text-sm text-zinc-300">
                    Description
                  </span>

                  <textarea
                    value={form.description}
                    onChange={(event) =>
                      updateField(
                        "description",
                        event.target.value,
                      )
                    }
                    placeholder="Project description"
                    rows={3}
                    className="mt-2 w-full resize-y rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                  />
                </label>

                <label className="block">
                  <span className="text-sm text-zinc-300">
                    Repository URL
                  </span>

                  <input
                    type="url"
                    value={form.repository_url}
                    onChange={(event) =>
                      updateField(
                        "repository_url",
                        event.target.value,
                      )
                    }
                    placeholder="https://github.com/username/repository"
                    className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                    required
                  />
                </label>

                <label className="block">
                  <span className="text-sm text-zinc-300">
                    Default branch
                  </span>

                  <input
                    value={form.default_branch}
                    onChange={(event) =>
                      updateField(
                        "default_branch",
                        event.target.value,
                      )
                    }
                    placeholder="main"
                    className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500"
                    required
                  />
                </label>

                <div className="flex justify-end gap-3 pt-3">
                  <button
                    type="button"
                    onClick={closeForm}
                    disabled={saving}
                    className="rounded-lg border border-zinc-700 px-4 py-2.5 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    disabled={saving}
                    className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {saving
                      ? "Saving..."
                      : editingProject
                        ? "Update project"
                        : "Create project"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
