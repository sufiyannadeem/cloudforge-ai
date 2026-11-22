"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useState,
} from "react";

import { useViewerSession } from "@/components/layout/ViewerSession";
import { canExecuteTerraform, canWriteProject } from "@/lib/role-access";
import AppShell from "@/components/layout/AppShell";
import ApplyApprovalModal, { type ReviewAction } from "@/components/infrastructure/ApplyApprovalModal";
import DestroyApprovalModal from "@/components/infrastructure/DestroyApprovalModal";
import DriftHistory from "@/components/infrastructure/DriftHistory";
import InfrastructureFields from "@/components/infrastructure/InfrastructureFields";
import { defaultInfrastructureValues, infrastructureConfiguration } from "@/lib/infrastructure-form";
import Link from "next/link";
import { waitForTerraformJob } from "@/lib/terraform-jobs";
import type {
  InfrastructureFormData,
  InfrastructureResource,
  InfrastructureStatus,
  PlanDetails,
} from "@/types/infrastructure";
import type { Project } from "@/types/projects";
import { getAnomalySummary } from "@/lib/anomaly-api";
import type { AnomalySummary } from "@/types/anomaly";
import {
  parseRightsizingParams,
  rightsizingDescription,
  type RightsizingRequest,
} from "@/lib/rightsizing";


const RESOURCES_API =
  "/api/proxy/infrastructure/api/v1/resources";

function csrfHeaders(): Record<string, string> {
  if (typeof document === "undefined") return {};
  const item = document.cookie.split(";").map((value) => value.trim())
    .find((value) => value.startsWith("cf_csrf="));
  if (!item) return {};
  return { "X-CSRF-Token": decodeURIComponent(item.slice("cf_csrf=".length)) };
}

const initialForm: InfrastructureFormData = {
  project_id: "",
  name: "",
  resource_type: "aws_vpc",
  provider: "aws",
  region: "eu-west-1",
  environment: "dev",
  configuration: defaultInfrastructureValues("aws_vpc"),
};

const statusClasses: Record<
  InfrastructureStatus,
  string
> = {
  pending:
    "bg-slate-500/10 text-slate-700 ring-1 ring-slate-500/20 dark:text-slate-300",
  planning:
    "bg-blue-500/10 text-blue-700 ring-1 ring-blue-500/20 dark:text-blue-300",
  awaiting_approval:
    "bg-amber-500/10 text-amber-700 ring-1 ring-amber-500/20 dark:text-amber-300",
  provisioning:
    "bg-indigo-500/10 text-indigo-700 ring-1 ring-indigo-500/20 dark:text-indigo-300",
  active:
    "bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/20 dark:text-emerald-300",
  inactive:
    "bg-slate-500/10 text-slate-700 ring-1 ring-slate-500/20 dark:text-slate-300",
  destroying:
    "bg-orange-500/10 text-orange-700 ring-1 ring-orange-500/20 dark:text-orange-300",
  awaiting_destroy_approval:
    "bg-rose-500/10 text-rose-700 ring-1 ring-rose-500/20 dark:text-rose-300",
  destroy_failed:
    "bg-red-500/10 text-red-700 ring-1 ring-red-500/20 dark:text-red-300",
  failed:
    "bg-red-500/10 text-red-700 ring-1 ring-red-500/20 dark:text-red-300",
  destroyed:
    "bg-slate-500/10 text-slate-700 ring-1 ring-slate-500/20 dark:text-slate-300",
};

function getResourceList(
  payload: unknown,
): InfrastructureResource[] {
  if (
    payload &&
    typeof payload === "object"
  ) {
    const value = payload as {
      items?: InfrastructureResource[];
      data?: InfrastructureResource[];
    };

    return value.items ?? value.data ?? [];
  }

  return [];
}

async function readError(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const contentType =
      response.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
      const payload = await response.json();

      return (
        payload?.error?.message ??
        payload?.message ??
        payload?.error ??
        fallback
      );
    }

    const text = await response.text();

    return text || fallback;
  } catch {
    return fallback;
  }
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function isApprovalExpired(
  resource: InfrastructureResource,
): boolean {
  if (!resource.approval_expires_at) {
    return false;
  }

  const expiresAt = new Date(
    resource.approval_expires_at,
  ).getTime();

  return (
    !Number.isNaN(expiresAt) &&
    expiresAt <= Date.now()
  );
}

export default function InfrastructurePage() {
  const [resources, setResources] = useState<
    InfrastructureResource[]
  >([]);
  const [projects, setProjects] = useState<Project[]>([]);

  const [form, setForm] =
    useState<InfrastructureFormData>(initialForm);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [planningId, setPlanningId] =
    useState<string | null>(null);

  const [applyingId, setApplyingId] =
    useState<string | null>(null);

  const [deletingId, setDeletingId] =
    useState<string | null>(null);

  const [destroyPlanningId, setDestroyPlanningId] =
    useState<string | null>(null);

  const [destroyingId, setDestroyingId] =
    useState<string | null>(null);

  // Resource whose destroy plan is currently shown in the approval modal.
  const [destroyTarget, setDestroyTarget] =
    useState<InfrastructureResource | null>(null);

  // Resource whose create plan is shown in the apply approval modal.
  const [applyTarget, setApplyTarget] =
    useState<InfrastructureResource | null>(null);

  const identity = useViewerSession();
  const [planDetails, setPlanDetails] = useState<PlanDetails | null>(null);
  const [reviewMessage, setReviewMessage] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [pendingOnly, setPendingOnly] = useState(false);
  const operator = canExecuteTerraform(identity?.role);
  const developer = identity?.role === "developer";
  const canRequest = operator || developer;

  const writableProjects = projects.filter(({ access_level }) => canWriteProject(identity?.role, access_level));
  const canManageRequest = (resource: InfrastructureResource) =>
    operator || (developer && writableProjects.some(({ id }) => id === resource.project_id));

  useEffect(() => {
    if (!operator || new URLSearchParams(window.location.search).get("review") !== "pending") return;
    const timer = window.setTimeout(() => setPendingOnly(true), 0);
    return () => window.clearTimeout(timer);
  }, [operator]);

  // FinOps rightsizing recommendation that pre-filled the request form.
  const [rightsizing, setRightsizing] =
    useState<RightsizingRequest | null>(null);

  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [aiopsInsights, setAiopsInsights] = useState<AnomalySummary | null>(null);

  const loadResources = useCallback(async (quiet = false) => {
    try {
      if (!quiet) {
        setLoading(true);
        setError("");
      }

      const response = await fetch(
        `${RESOURCES_API}?limit=100${pendingOnly ? "&review_status=submitted" : ""}`,
        {
          cache: "no-store",
        },
      );

      if (!response.ok) {
        throw new Error(
          await readError(
            response,
            "Failed to load infrastructure resources",
          ),
        );
      }

      const payload = await response.json();

      setResources(getResourceList(payload));
    } catch (requestError) {
      if (!quiet) setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load infrastructure resources",
      );
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [pendingOnly]);

  useEffect(() => {
    const initial = window.setTimeout(() => void loadResources(), 0);
    const timer = window.setInterval(() => void loadResources(true), 15_000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [loadResources]);

  useEffect(() => {
    if (!identity?.role) return;
    // FinOps "Apply Rightsizing" hand-off: pre-fill a new EC2 request with the
    // recommended instance type. Nothing is provisioned until the human
    // generates, reviews and approves the Terraform plan.
    const prefill = window.setTimeout(() => {
      const request = parseRightsizingParams(window.location.search);

      if (request) {
        const base = defaultInfrastructureValues("aws_ec2");

        setRightsizing(request);
        setForm((prev) => ({
          ...prev,
          resource_type: "aws_ec2",
          name: `rightsized-${request.toInstanceType.replace(".", "-")}-${Date.now().toString(36)}`,
          configuration: { ...base, instance_type: request.toInstanceType },
        }));
        setShowForm(true);
        window.history.replaceState(null, "", window.location.pathname);
      }
    }, 0);

    fetch("/api/proxy/project/projects?limit=50&offset=0")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) {
          const list = (data.data ?? data.items ?? []) as Project[];
          setProjects(list);
          if (list.length > 0) {
            setForm((prev) => (prev.project_id ? prev : { ...prev, project_id: list[0].id }));
          }
        }
      })
      .catch(() => {});

    // Refresh AIOps anomaly intelligence every 60 seconds.
const refreshAiopsInsights = async () => {
  try {
    const summary = await getAnomalySummary(
      "deployment-service",
      60,
      60,
    );
    setAiopsInsights(summary);
  } catch {
    // Clear stale alerts if the AIOps service becomes unavailable.
    setAiopsInsights(null);
  }
};

if (!developer) void refreshAiopsInsights();

const aiopsRefreshInterval = window.setInterval(() => {
  if (!developer) void refreshAiopsInsights();
}, 60_000);

return () => {
  window.clearTimeout(prefill);
  window.clearInterval(aiopsRefreshInterval);
};
  }, [identity?.role, developer]);

  const updateField = (
    field: Exclude<keyof InfrastructureFormData, "configuration">,
    value: string,
  ) => {
    setForm((current) => {
      const updated = {
        ...current,
        [field]: value,
      };
      if (field === "resource_type" && current.resource_type !== value) {
        updated.configuration = defaultInfrastructureValues(value);
      }
      return updated;
    });
  };

  const createResource = async (
    event: FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();

    try {
      setSaving(true);
      setError("");

      if (!writableProjects.some(({ id }) => id === form.project_id)) throw new Error("Select a project you can manage.");

      const configuration = infrastructureConfiguration(form.resource_type, form.configuration);
      const response = await fetch(
        RESOURCES_API,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...csrfHeaders(),
          },
          body: JSON.stringify({
            project_id:
              form.project_id || undefined,
            name: form.name,
            resource_type:
              form.resource_type,
            provider: form.provider,
            region: form.region,
            environment:
              form.environment,
            description: rightsizing
              ? rightsizingDescription(rightsizing)
              : undefined,
            configuration,
          }),
        },
      );

      if (!response.ok) {
        throw new Error(
          await readError(
            response,
            "Failed to create infrastructure resource",
          ),
        );
      }

      const created = (await response.json()) as InfrastructureResource;
      setForm(initialForm);
      setRightsizing(null);
      setShowForm(false);

      await planResource(created, true);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to create infrastructure resource",
      );
    } finally {
      setSaving(false);
    }
  };

  const planResource = async (
    resource: InfrastructureResource,
    justCreated = false,
  ) => {
    try {
      setPlanningId(resource.id);
      setError("");

      let response = await fetch(
        `${RESOURCES_API}/${resource.id}/plan`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            ...csrfHeaders(),
          },
        },
      );

      response = await waitForTerraformJob(response, `${RESOURCES_API}/${resource.id}`);

      if (!response.ok) {
        throw new Error(
          await readError(
            response,
            "Terraform plan failed",
          ),
        );
      }

      const planned =
        (await response.json()) as InfrastructureResource;

      await openPlan(planned);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Terraform plan failed";
      setError(justCreated ? `Request saved. ${message} Use Generate plan to retry.` : message);
    } finally {
      await loadResources(true);
      setPlanningId(null);
    }
  };

  const fetchPlan = async (id: string) => {
    const response = await fetch(`${RESOURCES_API}/${id}/plan`, { cache: "no-store" });
    if (!response.ok) throw new Error(await readError(response, "Saved plan unavailable"));
    setPlanDetails((await response.json()) as PlanDetails);
  };

  const openPlan = async (resource: InfrastructureResource, destroy = false) => {
    setApplyTarget(destroy ? null : resource);
    setDestroyTarget(destroy ? resource : null);
    setPlanDetails(null);
    setReviewMessage("");
    try {
      await fetchPlan(resource.id);
    } catch (err) {
      setReviewMessage(err instanceof Error ? err.message : "Saved plan unavailable");
    }
  };

  const decidePlan = async (action: ReviewAction) => {
    if (!planDetails) return;
    const { resource_id, operation, plan_hash, revision } = planDetails;
    setReviewBusy(true);
    setReviewMessage("");
    try {
      const response = await fetch(`${RESOURCES_API}/${resource_id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...csrfHeaders() },
        body: JSON.stringify({ action, operation, plan_hash, revision }),
      });
      if (!response.ok) throw new Error(await readError(response, "Plan review failed"));
      setReviewMessage({ submit: "Plan submitted for approval.", approve: "Plan approved.", reject: "Plan rejected." }[action]);
      await Promise.all([loadResources(true), fetchPlan(resource_id)]);
    } catch (err) {
      setReviewMessage(err instanceof Error ? err.message : "Plan review failed");
    } finally {
      setReviewBusy(false);
    }
  };

  const applyResource = async (
    resource: InfrastructureResource,
  ) => {
    if (!resource.plan_hash) {
      setError(
        "Cannot apply this resource because the Terraform plan hash is missing.",
      );
      return;
    }

    if (
      isApprovalExpired(resource)
    ) {
      setError(
        "The Terraform plan approval window has expired. Generate a new plan before applying.",
      );
      return;
    }

    try {
      setApplyingId(resource.id);
      setError("");

      let response = await fetch(
        `${RESOURCES_API}/${resource.id}/apply`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type":
              "application/json",
            ...csrfHeaders(),
          },
          body: JSON.stringify({
            plan_hash:
              resource.plan_hash,
          }),
        },
      );

      response = await waitForTerraformJob(response, `${RESOURCES_API}/${resource.id}`);

      if (!response.ok) {
        throw new Error(
          await readError(
            response,
            "Terraform apply failed",
          ),
        );
      }

      setApplyTarget(null);
      await loadResources();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Terraform apply failed",
      );
      setApplyTarget(null);
    } finally {
      setApplyingId(null);
    }
  };

  // Step 1 of teardown: generate a hashed destroy plan. Nothing is destroyed yet.
  const planDestroy = async (
    resource: InfrastructureResource,
  ) => {
    try {
      setDestroyPlanningId(resource.id);
      setError("");

      let response = await fetch(
        `${RESOURCES_API}/${resource.id}/destroy/plan`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            ...csrfHeaders(),
          },
        },
      );

      response = await waitForTerraformJob(response, `${RESOURCES_API}/${resource.id}`);

      if (!response.ok) {
        throw new Error(
          await readError(
            response,
            "Terraform destroy plan failed",
          ),
        );
      }

      const planned =
        (await response.json()) as InfrastructureResource;

      await openPlan(planned, true);

      await loadResources();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Terraform destroy plan failed",
      );
    } finally {
      setDestroyPlanningId(null);
    }
  };

  // Step 2 of teardown: explicit human approval of the reviewed plan hash.
  const applyDestroy = async (
    resource: InfrastructureResource,
  ) => {
    if (!resource.destroy_plan_hash) {
      setError(
        "Cannot destroy this resource because the destroy plan hash is missing.",
      );
      return;
    }

    try {
      setDestroyingId(resource.id);
      setError("");

      let response = await fetch(
        `${RESOURCES_API}/${resource.id}/destroy/apply`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type":
              "application/json",
            ...csrfHeaders(),
          },
          body: JSON.stringify({
            plan_hash:
              resource.destroy_plan_hash,
          }),
        },
      );

      response = await waitForTerraformJob(response, `${RESOURCES_API}/${resource.id}`);

      if (!response.ok) {
        throw new Error(
          await readError(
            response,
            "Terraform destroy failed",
          ),
        );
      }

      setDestroyTarget(null);
    } catch (requestError) {
      // Close the modal so the error banner remains visible.
      setDestroyTarget(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Terraform destroy failed",
      );
    } finally {
      setDestroyingId(null);
      await loadResources();
    }
  };

  const deleteResource = async (
    resource: InfrastructureResource,
  ) => {
    const confirmed = window.confirm(
      `Delete infrastructure resource "${resource.name}"?`,
    );

    if (!confirmed) {
      return;
    }

    try {
      setDeletingId(resource.id);
      setError("");

      const response = await fetch(
        `${RESOURCES_API}/${resource.id}`,
        {
          method: "DELETE",
          headers: csrfHeaders(),
        },
      );

      if (!response.ok) {
        throw new Error(
          await readError(
            response,
            "Failed to delete infrastructure resource",
          ),
        );
      }

      await loadResources();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to delete infrastructure resource",
      );
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-[1600px] space-y-8 p-4 sm:p-6 lg:p-8">
        <div className="mx-auto w-full max-w-[1600px]">
          <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-[var(--cf-text)]">
                Infrastructure
              </h1>

              <p className="mt-2 text-[var(--cf-text-secondary)]">
                Provision and manage AWS infrastructure through
                Terraform with human approval gates.
              </p>
            </div>

            <div className="flex items-center gap-3">
              {identity && <Link
                href={developer ? "/project-costs" : "/finops"}
                className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-4 py-2.5 text-sm font-semibold text-[var(--cf-text)] shadow-sm transition hover:bg-[var(--cf-surface-2)]"
              >
                {developer ? "Project FinOps" : "FinOps Intelligence"}
              </Link>}

              {canRequest && <button
                type="button"
                onClick={() =>
                  setShowForm(
                    (current) => !current,
                  )
                }
                className="rounded-lg bg-indigo-600 px-4 py-2.5 font-semibold text-white shadow-sm transition hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
              >
                {showForm
                  ? "Cancel"
                  : "Create Request"}
              </button>}
            </div>
          </div>

          {error && (
            <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-700 dark:text-red-300">
              {error}
            </div>
          )}

          {/* ── AIOps Scaling Intelligence ──────────────────────────────── */}
          {aiopsInsights && (aiopsInsights.anomaly_count > 0 || aiopsInsights.critical_count > 0) && (() => {
            const isCritical = aiopsInsights.overall_classification === "critical";
            const anomalyMetrics = aiopsInsights.metrics.filter(
              (m) => m.classification === "anomaly" || m.classification === "critical",
            );
            return (
              <div
                className={`mb-6 rounded-xl border p-5 shadow-sm ${
                  isCritical
                    ? "border-rose-500/30 bg-rose-500/10"
                    : "border-amber-500/30 bg-amber-500/10"
                }`}
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-full px-2.5 py-1 text-xs font-bold uppercase ${
                          isCritical
                            ? "bg-rose-500/20 text-rose-700 dark:text-rose-300"
                            : "bg-amber-500/20 text-amber-700 dark:text-amber-300"
                        }`}
                      >
                        {isCritical ? "🔴 AIOps Critical" : "🟡 AIOps Anomaly"}
                      </span>
                      <span className="text-xs font-medium text-[var(--cf-text-secondary)]">
                        Service: {aiopsInsights.service} · Window: {aiopsInsights.window_minutes}m
                      </span>
                    </div>
                    <p className={`text-sm font-semibold ${isCritical ? "text-rose-700 dark:text-rose-300" : "text-amber-700 dark:text-amber-300"}`}>
                      {aiopsInsights.critical_count > 0
                        ? `${aiopsInsights.critical_count} critical metric${aiopsInsights.critical_count > 1 ? "s" : ""} detected — scaling may be required`
                        : `${aiopsInsights.anomaly_count} anomalous metric${aiopsInsights.anomaly_count > 1 ? "s" : ""} detected — review recommended`}
                    </p>
                    <p className="text-xs text-[var(--cf-text-secondary)]">
                      AIOps has detected statistical deviations beyond baseline. Review below and provision scaling infrastructure if warranted.
                    </p>
                  </div>

                  {operator && isCritical && (
                    <button
                      type="button"
                      onClick={() => {
                        setForm((prev) => ({
                          ...prev,
                          resource_type: "aws_ec2",
                          name: `scaling-${aiopsInsights.service}-${Date.now().toString(36)}`,
                          configuration: defaultInfrastructureValues("aws_ec2"),
                        }));
                        setShowForm(true);
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                      className="shrink-0 self-start rounded-lg bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-500"
                    >
                      Create EC2 Scaling Request →
                    </button>
                  )}
                </div>

                {anomalyMetrics.length > 0 && (
                  <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {anomalyMetrics.slice(0, 6).map((metric) => (
                      <div
                        key={metric.name}
                        className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)]/60 p-3"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-[var(--cf-text)]">
                            {metric.display_name}
                          </span>
                          <span className={`text-xs font-bold ${
                            metric.classification === "critical"
                              ? "text-rose-600 dark:text-rose-400"
                              : "text-amber-600 dark:text-amber-400"
                          }`}>
                            {metric.direction === "increase" ? "↑" : metric.direction === "decrease" ? "↓" : "→"}
                          </span>
                        </div>
                        <div className="mt-1 flex items-baseline gap-1.5">
                          <span className="text-base font-bold text-[var(--cf-text)]">
                            {metric.current_value !== null ? metric.current_value.toFixed(2) : "—"}
                          </span>
                          <span className="text-xs text-[var(--cf-text-muted)]">{metric.unit}</span>
                        </div>
                        {metric.z_score !== null && (
                          <p className="mt-0.5 text-[10px] text-[var(--cf-text-muted)]">
                            z-score: {metric.z_score.toFixed(2)} · baseline: {metric.baseline_value?.toFixed(2) ?? "—"} {metric.unit}
                          </p>
                        )}
                        {metric.evidence.length > 0 && (
                          <p className="mt-1 text-[10px] italic text-[var(--cf-text-muted)]">{metric.evidence[0]}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}

          {canRequest && showForm && (
            <form
              onSubmit={createResource}
              className="mb-8 rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-sm"
            >
              <div className="mb-5">
                <h2 className="text-xl font-semibold text-[var(--cf-text)]">
                  Create Infrastructure Resource
                </h2>

                <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
                  Save the request and generate its plan. AWS changes require a Platform Engineer to approve and execute the saved plan.
                </p>
              </div>

              {rightsizing && (
                <div className="mb-5 rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-4 text-sm">
                  <p className="font-semibold text-indigo-700 dark:text-indigo-300">
                    FinOps rightsizing request: {rightsizing.fromInstanceType} →{" "}
                    {rightsizing.toInstanceType}
                    {rightsizing.monthlySavingsUsd > 0 &&
                      ` · save $${rightsizing.monthlySavingsUsd.toFixed(2)}/mo`}
                  </p>
                  <p className="mt-1 text-xs text-[var(--cf-text-secondary)]">
                    {rightsizing.rationale ||
                      "Recommended by CloudForge FinOps."}{" "}
                    Source: {rightsizing.resourceId || "unknown"}. This rationale is saved
                    on the new resource. AWS only changes after you generate, review and
                    approve the Terraform plan.
                  </p>
                </div>
              )}

              <div className="grid gap-4 md:grid-cols-2">
                {writableProjects.length > 0 ? (
                  <select
                    required
                    value={form.project_id}
                    onChange={(event) =>
                      updateField("project_id", event.target.value)
                    }
                    className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                  >
                    <option value="">Select Project</option>
                    {writableProjects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="p-3 text-sm">No authorized project available.</p>
                )}

                <input
                  required
                  placeholder="Resource name"
                  value={form.name}
                  onChange={(event) =>
                    updateField(
                      "name",
                      event.target.value,
                    )
                  }
                  className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] placeholder:text-[var(--cf-text-muted)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                />

                <select
                  value={form.resource_type}
                  onChange={(event) =>
                    updateField(
                      "resource_type",
                      event.target.value,
                    )
                  }
                  className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                >
                  <option value="aws_vpc">
                    AWS VPC (Virtual Private Cloud)
                  </option>
                  <option value="aws_ec2">
                    AWS EC2 (Compute Instance)
                  </option>
                  <option value="aws_s3">
                    AWS S3 (Object Storage)
                  </option>
                  <option value="aws_rds">
                    AWS RDS (Relational Database)
                  </option>
                  <option value="aws_eks">
                    AWS EKS (Kubernetes Cluster)
                  </option>
                  <option value="aws_lb">
                    AWS ALB (Application Load Balancer)
                  </option>
                </select>

                <select
                  value={form.environment}
                  onChange={(event) =>
                    updateField(
                      "environment",
                      event.target.value,
                    )
                  }
                  className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                >
                  <option value="dev">
                    Development
                  </option>

                  <option value="staging">
                    Staging
                  </option>

                  <option value="prod">
                    Production
                  </option>
                </select>

                <input
                  required
                  placeholder="AWS region"
                  aria-label="AWS region"
                  pattern="[a-z]{2}(?:-[a-z]+)+-[0-9]+"
                  value={form.region}
                  onChange={(event) =>
                    updateField(
                      "region",
                      event.target.value,
                    )
                  }
                  className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] placeholder:text-[var(--cf-text-muted)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                />
              </div>


              <InfrastructureFields type={form.resource_type} values={form.configuration}
                onChange={(key, value) => setForm((current) => ({
                  ...current, configuration: { ...current.configuration, [key]: value },
                }))} />

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-lg bg-indigo-600 px-5 py-2.5 font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {saving
                    ? "Saving and planning…"
                    : "Save request and generate plan"}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setForm(initialForm);
                    setRightsizing(null);
                  }}
                  disabled={saving}
                  className="rounded-lg border border-[var(--cf-border)] px-5 py-2.5 font-medium text-[var(--cf-text-secondary)] transition hover:bg-[var(--cf-surface-2)] disabled:opacity-50"
                >
                  Reset
                </button>
              </div>
            </form>
          )}

          <div className="mb-4 rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="font-semibold text-[var(--cf-text)]">
                  Provisioning workflow
                </p>

                <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
                  Request → Plan → Submit → Review → Apply
                </p>
              </div>

              <div className="text-xs text-[var(--cf-text-muted)]">
                Terraform apply is never automatic.
              </div>
            </div>
          </div>

          {operator && <label className="mb-3 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={pendingOnly} onChange={(event) => setPendingOnly(event.target.checked)} />
            Pending reviews only
          </label>}
          <div className="overflow-hidden rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] shadow-sm">
            {loading ? (
              <p className="p-6 text-[var(--cf-text-secondary)]">
                Loading resources...
              </p>
            ) : resources.length === 0 ? (
              <div className="p-8 text-center">
                <p className="font-medium text-[var(--cf-text)]">
                  {pendingOnly ? "No pending reviews." : "No infrastructure resources found."}
                </p>

                <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
                  Create your first CloudForge infrastructure
                  resource to begin.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead className="border-b border-[var(--cf-border)] bg-[var(--cf-surface-2)]">
                    <tr>
                      <th className="p-4">
                        Resource
                      </th>

                      <th className="p-4">
                        Type
                      </th>

                      <th className="p-4">
                        Environment
                      </th>

                      <th className="p-4">
                        Region
                      </th>

                      <th className="p-4">
                        Status
                      </th>

                      <th className="p-4">
                        Actions
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {resources.map(
                      (resource) => {
                        const approvalExpired =
                          isApprovalExpired(
                            resource,
                          );

                        return (
                          <tr
                            key={resource.id}
                            className="border-b border-[var(--cf-border)] align-top transition-colors hover:bg-[var(--cf-surface-2)]"
                          >
                            <td className="p-4">
                              <div className="font-medium text-[var(--cf-text)]">
                                {resource.name}
                              </div>

                              <div className="mt-1 text-xs text-[var(--cf-text-muted)]">
                                {resource.provider}
                              </div>
                            </td>

                            <td className="p-4 text-sm text-[var(--cf-text-secondary)]">
                              {resource.resource_type}
                            </td>

                            <td className="p-4 text-sm text-[var(--cf-text-secondary)]">
                              {resource.environment}
                            </td>

                            <td className="p-4 text-sm text-[var(--cf-text-secondary)]">
                              {resource.region}
                            </td>

                            <td className="p-4">
                              <span
                                className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${
                                  statusClasses[
                                    resource.status
                                  ]
                                }`}
                              >
                                {resource.status}
                              </span>
                              <DriftHistory
                                resourceId={resource.id}
                                scanAllowed={resource.status === "active" && (operator || identity?.role === "sre")}
                                onPlan={operator && resource.status === "active" && planningId !== resource.id ? () => void planResource(resource) : undefined}
                              />
                            </td>

                            <td className="min-w-[330px] p-4">
                              <div className="flex flex-wrap gap-2">
                                {canManageRequest(resource) && (resource.status ===
                                  "pending" ||
                                  resource.status ===
                                    "failed" ||
                                  resource.status ===
                                    "planning") && (
                                  <button
                                    type="button"
                                    disabled={
                                      planningId ===
                                      resource.id
                                    }
                                    onClick={() =>
                                      void planResource(
                                        resource,
                                      )
                                    }
                                    className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    {planningId ===
                                    resource.id
                                      ? "Planning..."
                                      : resource.status === "planning"
                                        ? "Retry plan"
                                        : "Generate Plan"}
                                  </button>
                                )}

                                {resource.status ===
                                  "awaiting_approval" && (
                                  <button
                                    type="button"
                                    disabled={
                                      applyingId ===
                                      resource.id
                                    }
                                    onClick={() =>
                                      void openPlan(
                                        resource,
                                      )
                                    }
                                    className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    {applyingId ===
                                    resource.id
                                      ? "Applying..."
                                      : approvalExpired
                                        ? "View expired plan"
                                        : "Review plan"}
                                  </button>
                                )}

                                {operator && (resource.status === "active" || resource.status === "destroy_failed" || resource.status === "failed") && (
                                  <button
                                    type="button"
                                    disabled={
                                      destroyPlanningId ===
                                      resource.id
                                    }
                                    onClick={() =>
                                      void planDestroy(
                                        resource,
                                      )
                                    }
                                    className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    {destroyPlanningId ===
                                    resource.id
                                      ? "Planning destroy..."
                                      : resource.status !== "active" ? "Reconcile and plan destroy" : "Teardown / Destroy"}
                                  </button>
                                )}

                                {resource.status ===
                                  "awaiting_destroy_approval" && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      void openPlan(resource, true)
                                    }
                                    className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm font-semibold text-rose-700 transition hover:bg-rose-500/20 dark:text-rose-300"
                                  >
                                    Review Destroy Plan
                                  </button>
                                )}

                                {resource.review_status && resource.status !== "awaiting_approval" &&
                                  resource.status !== "awaiting_destroy_approval" && (
                                  <button type="button" onClick={() => void openPlan(resource, resource.status === "destroy_failed")}
                                    className="rounded-lg border border-[var(--cf-border)] px-3 py-2 text-sm">
                                    Review history
                                  </button>
                                )}
                                {operator && (resource.status ===
                                  "pending" ||
                                  resource.status ===
                                    "failed" ||
                                  resource.status ===
                                    "destroyed" ||
                                  resource.status ===
                                    "inactive") && (
                                <button
                                  type="button"
                                  disabled={
                                    deletingId ===
                                    resource.id
                                  }
                                  onClick={() =>
                                    void deleteResource(
                                      resource,
                                    )
                                  }
                                  className="rounded-lg border border-red-500/30 px-3 py-2 text-sm font-medium text-red-600 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50 dark:text-red-300"
                                >
                                  {deletingId ===
                                  resource.id
                                    ? "Deleting..."
                                    : "Delete"}
                                </button>
                                )}
                              </div>

                              {resource.status ===
                                "awaiting_approval" && (
                                <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                                  <p className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">
                                    {resource.review_status === "approved" ? "Approved · ready to execute" : resource.review_status === "submitted" ? "Awaiting review" : "Draft · needs submission"}
                                  </p>

                                  <dl className="mt-2 space-y-1 text-xs text-[var(--cf-text-secondary)]">
                                    <div>
                                      <dt className="inline font-medium">
                                        Plan created:
                                      </dt>{" "}
                                      <dd className="inline">
                                        {formatDate(
                                          resource.plan_created_at,
                                        )}
                                      </dd>
                                    </div>

                                    <div>
                                      <dt className="inline font-medium">
                                        Approval expires:
                                      </dt>{" "}
                                      <dd className="inline">
                                        {formatDate(
                                          resource.approval_expires_at,
                                        )}
                                      </dd>
                                    </div>

                                    <div>
                                      <dt className="inline font-medium">
                                        Plan SHA-256:
                                      </dt>{" "}
                                      <dd className="mt-1 block break-all font-mono">
                                        {resource.plan_hash ??
                                          "—"}
                                      </dd>
                                    </div>


                                  </dl>
                                </div>
                              )}

                              {resource.status ===
                                "planning" && (
                                <p className="mt-2 text-xs text-[var(--cf-text-muted)]">
                                  Terraform is generating the
                                  infrastructure plan.
                                </p>
                              )}

                              {resource.status ===
                                "provisioning" && (
                                <p className="mt-2 text-xs text-[var(--cf-text-muted)]">
                                  Terraform apply is currently
                                  running.
                                </p>
                              )}

                              {resource.status ===
                                "active" && (
                                <div className="mt-2 flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                                  Terraform workflow complete. Live AWS status unverified.
                                </div>
                              )}

                              {resource.terraform_resource_id && (
                                <p className="mt-2 break-all text-xs text-[var(--cf-text-muted)]">
                                  Last Terraform state ID {resource.terraform_resource_id}
                                </p>
                              )}
                              {resource.aws_last_verified_at && (
                                <p className="mt-1 text-xs text-[var(--cf-text-muted)]">
                                  Last AWS provider verification {formatDate(resource.aws_last_verified_at)}
                                </p>
                              )}
                              {resource.last_execution_error && (
                                <p className="mt-2 text-xs text-red-600">{resource.last_execution_error}</p>
                              )}
                              {resource.status === "destroy_failed" && (
                                <p className="mt-2 text-xs text-red-600">
                                  Destroy failed. Reconcile with a fresh Terraform plan and approval before retrying.
                                </p>
                              )}

                              {resource.status ===
                                "destroying" && (
                                <p className="mt-2 text-xs text-[var(--cf-text-muted)]">
                                  Terraform destroy is currently
                                  running.
                                </p>
                              )}

                              {resource.status ===
                                "awaiting_destroy_approval" && (
                                <p className="mt-2 text-xs font-medium text-rose-600 dark:text-rose-300">
                                  A destroy plan is waiting for
                                  human approval.
                                </p>
                              )}

                              {resource.status ===
                                "destroyed" && (
                                <p className="mt-2 text-xs text-[var(--cf-text-muted)]">
                                  Destroyed on AWS. No longer
                                  monitored as active
                                  infrastructure.
                                </p>
                              )}

                              {resource.status ===
                                "failed" && (
                                <p className="mt-2 text-xs text-red-600 dark:text-red-300">
                                  The previous provisioning
                                  operation failed. Generate a
                                  new plan before retrying.
                                </p>
                              )}
                            </td>
                          </tr>
                        );
                      },
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {applyTarget && (
        <ApplyApprovalModal resource={applyTarget} plan={planDetails?.resource_id === applyTarget.id ? planDetails : null}
          operator={operator} developer={developer && canManageRequest(applyTarget)} username={identity?.username ?? ""}
          busy={reviewBusy || applyingId === applyTarget.id || planningId === applyTarget.id}
          message={reviewMessage} onDecision={(action) => void decidePlan(action)}
          onConfirm={() => { if (planDetails?.resource_id === applyTarget.id) void applyResource({ ...applyTarget, plan_hash: planDetails.plan_hash, approval_expires_at: planDetails.approval_expires_at }); }} onReplan={() => void planResource(applyTarget)}
          onClose={() => setApplyTarget(null)} />
      )}

      {destroyTarget && (
        <DestroyApprovalModal resource={destroyTarget} plan={planDetails?.resource_id === destroyTarget.id ? planDetails : null}
          operator={operator} developer={false} username={identity?.username ?? ""}
          busy={reviewBusy || destroyingId === destroyTarget.id || destroyPlanningId === destroyTarget.id}
          message={reviewMessage} onDecision={(action) => void decidePlan(action)}
          onConfirm={() => { if (planDetails?.resource_id === destroyTarget.id) void applyDestroy({ ...destroyTarget, destroy_plan_hash: planDetails.plan_hash, approval_expires_at: planDetails.approval_expires_at }); }} onReplan={() => void planDestroy(destroyTarget)}
          onClose={() => setDestroyTarget(null)} />
      )}
    </AppShell>
  );
}
