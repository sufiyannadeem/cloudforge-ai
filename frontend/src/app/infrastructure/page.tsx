"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useState,
} from "react";

import AppShell from "@/components/layout/AppShell";
import ApplyApprovalModal from "@/components/infrastructure/ApplyApprovalModal";
import DestroyApprovalModal from "@/components/infrastructure/DestroyApprovalModal";
import Link from "next/link";
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

const DEFAULT_CONFIGS: Record<string, string> = {
  aws_vpc: JSON.stringify(
    {
      cidr_block: "10.0.0.0/16",
      enable_dns_hostnames: true,
      enable_dns_support: true,
    },
    null,
    2
  ),
  aws_ec2: JSON.stringify(
    {
      instance_type: "t3.micro",
      ami_id: "ami-0c55b159cbfafe1f0",
      associate_public_ip_address: true,
    },
    null,
    2
  ),
  aws_s3: JSON.stringify(
    {
      bucket: "cloudforge-app-bucket",
      versioning: true,
      force_destroy: false,
    },
    null,
    2
  ),
  aws_rds: JSON.stringify(
    {
      engine: "postgres",
      engine_version: "16.3",
      instance_class: "db.t4g.micro",
      allocated_storage: 20,
      database_name: "cloudforge",
      username: "cloudforge_admin",
      skip_final_snapshot: true,
    },
    null,
    2
  ),
  aws_eks: JSON.stringify(
    {
      cluster_version: "1.30",
      subnet_ids: ["subnet-0123456789abcdef0", "subnet-0fedcba9876543210"],
      node_instance_types: ["t3.medium"],
      desired_capacity: 2,
      min_capacity: 1,
      max_capacity: 4,
    },
    null,
    2
  ),
  aws_lb: JSON.stringify(
    {
      load_balancer_type: "application",
      internal: false,
      subnet_ids: ["subnet-0123456789abcdef0", "subnet-0fedcba9876543210"],
      port: 80,
      protocol: "HTTP",
    },
    null,
    2
  ),
};

const ESTIMATED_MONTHLY_COST: Record<string, string> = {
  aws_vpc: "$0.00 / mo",
  aws_ec2: "$10.40 / mo (t3.micro)",
  aws_s3: "$5.00 / mo (standard tier)",
  aws_rds: "$18.50 / mo (db.t4g.micro + 20GB)",
  aws_eks: "$73.00 / mo (cluster) + compute",
  aws_lb: "$22.50 / mo (ALB base rate)",
};

const initialForm: InfrastructureFormData = {
  project_id: "",
  name: "",
  resource_type: "aws_vpc",
  provider: "aws",
  region: "eu-west-1",
  environment: "dev",
  configuration: DEFAULT_CONFIGS.aws_vpc,
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

  // FinOps rightsizing recommendation that pre-filled the request form.
  const [rightsizing, setRightsizing] =
    useState<RightsizingRequest | null>(null);

  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [aiopsInsights, setAiopsInsights] = useState<AnomalySummary | null>(null);

  const loadResources = useCallback(async () => {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        RESOURCES_API,
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
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load infrastructure resources",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial data load on page mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadResources();

    // FinOps "Apply Rightsizing" hand-off: pre-fill a new EC2 request with the
    // recommended instance type. Nothing is provisioned until the human
    // generates, reviews and approves the Terraform plan.
    const request = parseRightsizingParams(window.location.search);

    if (request) {
      const base = JSON.parse(DEFAULT_CONFIGS.aws_ec2) as Record<string, unknown>;

      setRightsizing(request);
      setForm((prev) => ({
        ...prev,
        resource_type: "aws_ec2",
        name: `rightsized-${request.toInstanceType.replace(".", "-")}-${Date.now().toString(36)}`,
        configuration: JSON.stringify(
          { ...base, instance_type: request.toInstanceType },
          null,
          2,
        ),
      }));
      setShowForm(true);
      window.history.replaceState(null, "", window.location.pathname);
    }

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

void refreshAiopsInsights();

const aiopsRefreshInterval = window.setInterval(() => {
  void refreshAiopsInsights();
}, 60_000);

return () => {
  window.clearInterval(aiopsRefreshInterval);
};
  }, [loadResources]);

  const updateField = (
    field: keyof InfrastructureFormData,
    value: string,
  ) => {
    setForm((current) => {
      const updated = {
        ...current,
        [field]: value,
      };
      if (field === "resource_type" && DEFAULT_CONFIGS[value]) {
        updated.configuration = DEFAULT_CONFIGS[value];
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

      let configuration: Record<
        string,
        unknown
      >;

      try {
        configuration = JSON.parse(
          form.configuration,
        );
      } catch {
        throw new Error(
          "Configuration must contain valid JSON",
        );
      }

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

      setForm(initialForm);
      setRightsizing(null);
      setShowForm(false);

      await loadResources();
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
  ) => {
    try {
      setPlanningId(resource.id);
      setError("");

      const response = await fetch(
        `${RESOURCES_API}/${resource.id}/plan`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            ...csrfHeaders(),
          },
        },
      );

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

      setApplyTarget(planned);
      await loadResources();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Terraform plan failed",
      );
    } finally {
      setPlanningId(null);
    }
  };

  const openApplyModal = async (
    resource: InfrastructureResource,
  ) => {
    setApplyTarget(resource);
    if (!resource.plan_summary) {
      try {
        const response = await fetch(
          `${RESOURCES_API}/${resource.id}/plan`,
          {
            headers: {
              Accept: "application/json",
              ...csrfHeaders(),
            },
          },
        );
        if (response.ok) {
          const details =
            (await response.json()) as PlanDetails;
          if (details.plan_summary) {
            setApplyTarget((prev) =>
              prev && prev.id === resource.id
                ? {
                    ...prev,
                    plan_summary:
                      details.plan_summary,
                  }
                : prev,
            );
          }
        }
      } catch {
        // Fall back gracefully to configuration display
      }
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

      const response = await fetch(
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

      const response = await fetch(
        `${RESOURCES_API}/${resource.id}/destroy/plan`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            ...csrfHeaders(),
          },
        },
      );

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

      setDestroyTarget(planned);

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

      const response = await fetch(
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
      // Close the modal so the error banner is visible; the backend returns the
      // resource to active, so a fresh destroy plan can be generated.
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
              <Link
                href="/finops"
                className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-4 py-2.5 text-sm font-semibold text-[var(--cf-text)] shadow-sm transition hover:bg-[var(--cf-surface-2)]"
              >
                FinOps Intelligence →
              </Link>

              <button
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
                  : "Create Resource"}
              </button>
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

                  {isCritical && (
                    <button
                      type="button"
                      onClick={() => {
                        setForm((prev) => ({
                          ...prev,
                          resource_type: "aws_ec2",
                          name: `scaling-${aiopsInsights.service}-${Date.now().toString(36)}`,
                          configuration: DEFAULT_CONFIGS.aws_ec2 ?? prev.configuration,
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

          {showForm && (
            <form
              onSubmit={createResource}
              className="mb-8 rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-sm"
            >
              <div className="mb-5">
                <h2 className="text-xl font-semibold text-[var(--cf-text)]">
                  Create Infrastructure Resource
                </h2>

                <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
                  This creates a CloudForge resource definition.
                  Terraform provisioning starts only when you
                  explicitly generate a plan.
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
                {projects.length > 0 ? (
                  <select
                    value={form.project_id}
                    onChange={(event) =>
                      updateField("project_id", event.target.value)
                    }
                    className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                  >
                    <option value="">Select Project</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    placeholder="Project ID"
                    value={form.project_id}
                    onChange={(event) =>
                      updateField(
                        "project_id",
                        event.target.value,
                      )
                    }
                    className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] placeholder:text-[var(--cf-text-muted)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                  />
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
                  placeholder="Provider"
                  value={form.provider}
                  onChange={(event) =>
                    updateField(
                      "provider",
                      event.target.value,
                    )
                  }
                  className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)] placeholder:text-[var(--cf-text-muted)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                />

                <input
                  required
                  placeholder="Region"
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

              <div className="mt-4 flex items-center justify-between rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-[var(--cf-text-secondary)]">
                    FinOps Plan Cost Preview:
                  </span>
                  <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                    {ESTIMATED_MONTHLY_COST[form.resource_type] ?? "$0.00 / mo"}
                  </span>
                </div>
                <Link
                  href="/finops"
                  className="text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
                >
                  Verify in FinOps →
                </Link>
              </div>

              <textarea
                required
                rows={8}
                value={form.configuration}
                onChange={(event) =>
                  updateField(
                    "configuration",
                    event.target.value,
                  )
                }
                className="mt-4 w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 font-mono text-sm text-[var(--cf-text)] placeholder:text-[var(--cf-text-muted)] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                placeholder='{"cidr_block":"10.50.0.0/16"}'
              />

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-lg bg-indigo-600 px-5 py-2.5 font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {saving
                    ? "Creating..."
                    : "Create Resource"}
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
                  Create → Plan → Review → Approve & Apply → Teardown (Destroy Plan → Approve)
                </p>
              </div>

              <div className="text-xs text-[var(--cf-text-muted)]">
                Terraform apply is never automatic.
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] shadow-sm">
            {loading ? (
              <p className="p-6 text-[var(--cf-text-secondary)]">
                Loading resources...
              </p>
            ) : resources.length === 0 ? (
              <div className="p-8 text-center">
                <p className="font-medium text-[var(--cf-text)]">
                  No infrastructure resources found.
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
                            </td>

                            <td className="min-w-[330px] p-4">
                              <div className="flex flex-wrap gap-2">
                                {(resource.status ===
                                  "pending" ||
                                  resource.status ===
                                    "failed") && (
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
                                      : "Generate Plan"}
                                  </button>
                                )}

                                {resource.status ===
                                  "awaiting_approval" && (
                                  <button
                                    type="button"
                                    disabled={
                                      applyingId ===
                                      resource.id ||
                                      approvalExpired
                                    }
                                    onClick={() =>
                                      void openApplyModal(
                                        resource,
                                      )
                                    }
                                    className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    {applyingId ===
                                    resource.id
                                      ? "Applying..."
                                      : approvalExpired
                                        ? "Plan Expired"
                                        : "Approve & Apply"}
                                  </button>
                                )}

                                {resource.status ===
                                  "active" && (
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
                                      : "Teardown / Destroy"}
                                  </button>
                                )}

                                {resource.status ===
                                  "awaiting_destroy_approval" && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setDestroyTarget(
                                        resource,
                                      )
                                    }
                                    className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm font-semibold text-rose-700 transition hover:bg-rose-500/20 dark:text-rose-300"
                                  >
                                    Review Destroy Plan
                                  </button>
                                )}

                                {resource.status !==
                                  "active" &&
                                  resource.status !==
                                    "awaiting_destroy_approval" &&
                                  resource.status !==
                                    "destroying" && (
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
                                    Human approval required
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

                                    <div className="pt-1 border-t border-amber-500/20 flex items-center justify-between">
                                      <div>
                                        <dt className="inline font-medium text-emerald-600 dark:text-emerald-400">
                                          Estimated Cost:
                                        </dt>{" "}
                                        <dd className="inline font-semibold text-emerald-700 dark:text-emerald-300">
                                          {ESTIMATED_MONTHLY_COST[resource.resource_type] ?? "~$15.00 / mo"}
                                        </dd>
                                      </div>
                                      <Link
                                        href="/finops"
                                        className="text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
                                      >
                                        Inspect in FinOps →
                                      </Link>
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
                                  Provisioned & active on AWS
                                </div>
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
        <ApplyApprovalModal
          resource={applyTarget}
          confirming={applyingId === applyTarget.id}
          replanning={planningId === applyTarget.id}
          onConfirm={() => void applyResource(applyTarget)}
          onReplan={() => void planResource(applyTarget)}
          onClose={() => setApplyTarget(null)}
        />
      )}

      {destroyTarget && (
        <DestroyApprovalModal
          resource={destroyTarget}
          confirming={destroyingId === destroyTarget.id}
          replanning={destroyPlanningId === destroyTarget.id}
          onConfirm={() => void applyDestroy(destroyTarget)}
          onReplan={() => void planDestroy(destroyTarget)}
          onClose={() => setDestroyTarget(null)}
        />
      )}
    </AppShell>
  );
}
