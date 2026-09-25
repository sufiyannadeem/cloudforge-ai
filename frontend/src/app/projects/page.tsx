"use client";

import { useCallback, useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
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
    <AppShell>
      <div className="mx-auto w-full max-w-[1600px] space-y-8 p-4 sm:p-6 lg:p-8">
      <div className="mx-auto w-full max-w-[1600px] space-y-8">
        <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
              CloudForge Platform
            </p>

            <h1 className="mt-2 text-3xl font-bold tracking-tight text-[var(--cf-text)]">
              Projects
            </h1>

            <p className="mt-2 text-sm text-[var(--cf-text-secondary)]">
              Manage repositories and project configuration.
            </p>
          </div>

          <button
            type="button"
            onClick={openCreateForm}
            className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold
            text-white shadow-sm transition hover:bg-indigo-500
            focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          >
            + Create project
          </button>
        </header>

        {error && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-300">
            {error}
          </div>
        )}

        <section className="overflow-hidden rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] shadow-sm">
          <div className="flex items-center justify-between border-b border-[var(--cf-border)] px-5 py-4">
            <div>
              <h2 className="font-semibold text-[var(--cf-text)]">
                All projects
              </h2>

              <p className="mt-1 text-xs text-[var(--cf-text-muted)]">
                {projects.length} project(s) loaded
              </p>
            </div>

            <button
              type="button"
              onClick={() => void loadProjects()}
              disabled={loading}
              className="rounded-lg border border-[var(--cf-border)]
              bg-[var(--cf-surface)]
              px-3 py-2 text-xs font-medium
              text-[var(--cf-text-secondary)]
              transition
              hover:bg-[var(--cf-surface-2)]
              hover:text-[var(--cf-text)]
              disabled:cursor-not-allowed
              disabled:opacity-50"
            >
              {loading ? "Loading..." : "Refresh"}
            </button>
          </div>

          {loading ? (
            <div className="px-5 py-16 text-center text-sm text-[var(--cf-text-muted)]">
              Loading projects...
            </div>
          ) : projects.length === 0 ? (
            <div className="px-5 py-16 text-center">
              <p className="text-sm text-[var(--cf-text-secondary)]">
                No projects found.
              </p>

              <button
                type="button"
                onClick={openCreateForm}
                className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
              >
                Create your first project
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-[var(--cf-border)] bg-[var(--cf-surface-2)] text-xs uppercase tracking-wide text-[var(--cf-text-secondary)]">
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

                <tbody className="divide-y divide-[var(--cf-border)]">
                  {projects.map((project) => (
                    <tr
                      key={project.id}
                      className="transition-colors hover:bg-[var(--cf-surface-2)]"
                    >
                      <td className="px-5 py-4">
                        <p className="font-medium text-[var(--cf-text)]">
                          {project.name}
                        </p>

                        <p className="mt-1 max-w-xs truncate text-xs text-[var(--cf-text-muted)]">
                          {project.description ||
                            "No description"}
                        </p>
                      </td>

                      <td className="max-w-xs px-5 py-4">
                        <a
                          href={project.repository_url}
                          target="_blank"
                          rel="noreferrer"
                          className="block truncate text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
                        >
                          {project.repository_url}
                        </a>
                      </td>

                      <td className="px-5 py-4 font-mono text-xs text-[var(--cf-text-secondary)]">
                        {project.default_branch}
                      </td>

                      <td className="px-5 py-4">
                        <span className="inline-flex items-center gap-1.5 rounded-full
                          bg-emerald-500/10 px-2.5 py-1
                          text-xs font-semibold capitalize
                          text-emerald-700 ring-1 ring-emerald-500/20
                          dark:text-emerald-300">
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
                            className="rounded-lg border border-[var(--cf-border)]
                              bg-[var(--cf-surface)]
                              px-3 py-1.5 text-xs font-medium
                              text-[var(--cf-text-secondary)]
                              transition
                              hover:bg-[var(--cf-surface-2)]
                              hover:text-[var(--cf-text)]"
                          >
                            Edit
                          </button>

                          <button
                            type="button"
                            onClick={() =>
                              void deleteProject(project)
                            }
                            className="rounded-lg border border-rose-500/30
                              bg-rose-500/5
                              px-3 py-1.5 text-xs font-medium
                              text-rose-600
                              transition
                              hover:bg-rose-500/10
                              dark:text-rose-400"
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
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--cf-overlay)] p-4 backdrop-blur-sm">
            <div className="w-full max-w-lg rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-2xl">
              <div className="flex items-start justify-between gap-4 border-b border-[var(--cf-border)] pb-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
                    Project configuration
                  </p>
                  <h2 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
                  {editingProject
                    ? "Edit project"
                    : "Create project"}
                  </h2>
                </div>

                <button
                  type="button"
                  onClick={closeForm}
                  disabled={saving}
                  className="text-xl text-[var(--cf-text-muted)] transition hover:text-[var(--cf-text)]"
                >
                  ×
                </button>
              </div>

              <form
                onSubmit={saveProject}
                className="mt-5 space-y-4"
              >
                <label className="block">
                  <span className="text-sm font-medium text-[var(--cf-text-secondary)]">
                    Project name
                  </span>

                  <input
                    value={form.name}
                    onChange={(event) =>
                      updateField("name", event.target.value)
                    }
                    placeholder="CloudForge Application"
                    className="mt-2 w-full rounded-lg border border-[var(--cf-border)]
                    bg-[var(--cf-surface)] px-3 py-2.5
                    text-sm text-[var(--cf-text)]
                    placeholder:text-[var(--cf-text-muted)]
                    outline-none transition
                    focus:border-indigo-500
                    focus:ring-2 focus:ring-indigo-500/20"
                    required
                  />
                </label>

                <label className="block">
                  <span className="text-sm font-medium text-[var(--cf-text-secondary)]">
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
                    className="mt-2 w-full resize-y rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-3 py-2.5 text-sm text-[var(--cf-text)] placeholder:text-[var(--cf-text-muted)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                  />
                </label>

                <label className="block">
                  <span className="text-sm font-medium text-[var(--cf-text-secondary)]">
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
                    className="mt-2 w-full rounded-lg border border-[var(--cf-border)]
                    bg-[var(--cf-surface)] px-3 py-2.5
                    text-sm text-[var(--cf-text)]
                    placeholder:text-[var(--cf-text-muted)]
                    outline-none transition
                    focus:border-indigo-500
                    focus:ring-2 focus:ring-indigo-500/20"
                    required
                  />
                </label>

                <label className="block">
                  <span className="text-sm font-medium text-[var(--cf-text-secondary)]">
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
                    className="mt-2 w-full rounded-lg border border-[var(--cf-border)]
                    bg-[var(--cf-surface)] px-3 py-2.5
                    text-sm text-[var(--cf-text)]
                    placeholder:text-[var(--cf-text-muted)]
                    outline-none transition
                    focus:border-indigo-500
                    focus:ring-2 focus:ring-indigo-500/20"
                    required
                  />
                </label>

                <div className="flex justify-end gap-3 pt-3">
                  <button
                    type="button"
                    onClick={closeForm}
                    disabled={saving}
                    className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-4 py-2.5 text-sm font-medium text-[var(--cf-text-secondary)] transition hover:border-[var(--cf-border-strong)] hover:bg-[var(--cf-surface-2)] hover:text-[var(--cf-text)] disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    disabled={saving}
                    className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
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
      </div>
    </AppShell>
  );
}
