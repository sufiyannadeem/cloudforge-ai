import { serviceAssertion, type Audience } from "@/lib/service-identity";
import { serviceConfig } from "@/lib/server-config";
import type { CloudForgeSession } from "@/lib/auth";
import { dashboardCapabilities } from "@/lib/role-access";
import type { FinOpsReport } from "@/types/finops";
import {
  getDeploymentProgress,
  getErrorRate,
  getP95Latency,
  getRequestRate,
  getRequestsInFlight,
  getServiceAvailability,
} from "@/lib/observability-api";
import type {
  DeploymentListResponse,
  InfrastructureListResponse,
  ProjectListResponse,
} from "@/types/api";
import type {
  DashboardData,
  DashboardObservability,
} from "@/types/dashboard";

const REQUEST_TIMEOUT_MS = 10_000;

interface IncidentListResponse {
  items?: unknown[];
  data?: unknown[];
  incidents?: unknown[];
  total?: number;
  count?: number;
  limit?: number;
  offset?: number;
}

function extractIncidentCount(
  data: IncidentListResponse,
): number | null {
  if (typeof data.total === "number") {
    return data.total;
  }

  if (typeof data.count === "number") {
    return data.count;
  }

  if (Array.isArray(data.incidents)) {
    return data.incidents.length;
  }

  if (Array.isArray(data.items)) {
    return data.items.length;
  }

  if (Array.isArray(data.data)) {
    return data.data.length;
  }

  return null;
}

async function getObservabilityData(): Promise<{
  observability: DashboardObservability;
  errors: string[];
}> {
  const errors: string[] = [];

  const results = await Promise.allSettled([
    getServiceAvailability(),
    getRequestRate(),
    getErrorRate(),
    getP95Latency(),
    getDeploymentProgress(),
    getRequestsInFlight(),
  ]);

  const serviceNames = [
    "service availability",
    "request rate",
    "error rate",
    "P95 latency",
    "deployment progress",
    "requests in flight",
  ];

  const values = results.map((result, index) => {
    if (result.status === "fulfilled") {
      return result.value;
    }

    errors.push(
      `Unable to load ${serviceNames[index]} from Prometheus`,
    );

    return null;
  });

  return {
    observability: {
      availability: values[0],
      requestRate: values[1],
      errorRate: values[2],
      p95Latency: values[3],
      deploymentsInProgress: values[4],
      requestsInFlight: values[5],
    },
    errors,
  };
}

export async function backendRequest(session: CloudForgeSession, audience: Audience, url: string, timeoutMs = REQUEST_TIMEOUT_MS) {
  return fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
      "X-CloudForge-Identity": serviceAssertion(audience, new URL(url), "GET", session),
    },
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(timeoutMs),
  });
}

async function authorizedJSON<T>(session: CloudForgeSession, audience: Audience, url: string): Promise<T> {
  const response = await backendRequest(session, audience, url);
  if (!response.ok) throw new Error(`Backend returned ${response.status}`);
  return response.json() as Promise<T>;
}

export function getAccessibleProjects(session: CloudForgeSession) {
  return authorizedJSON<ProjectListResponse>(session, "project", `${serviceConfig.project}/projects?limit=100&offset=0`);
}

export async function getDashboardData(session: CloudForgeSession): Promise<DashboardData> {
  const errors: string[] = [];
  const capabilities = dashboardCapabilities(session.role);
  const load = async <T>(label: string, request: () => Promise<T>) => {
    try {
      return await request();
    } catch {
      errors.push(`Unable to load ${label}.`);
      return null;
    }
  };

  const [projects, infrastructure, deployments, incidents, telemetry, pending, report] = await Promise.all([
    load("projects", () => getAccessibleProjects(session)),
    load("infrastructure", () => authorizedJSON<InfrastructureListResponse>(session, "infrastructure",
      `${serviceConfig.infrastructure}/api/v1/resources?limit=100&offset=0`)),
    load("deployments", () => authorizedJSON<DeploymentListResponse>(session, "deployment",
      `${serviceConfig.deployment}/api/v1/deployments?limit=100&offset=0`)),
    capabilities.platformTelemetry ? load("incidents", () => authorizedJSON<IncidentListResponse>(session, "aiops",
      `${serviceConfig.aiops}/api/v1/incidents?limit=100&offset=0`)) : null,
    capabilities.platformTelemetry ? getObservabilityData() : null,
    capabilities.approvalQueue ? load("Terraform approvals", () => authorizedJSON<InfrastructureListResponse>(session, "infrastructure",
      `${serviceConfig.infrastructure}/api/v1/resources?limit=100&review_status=submitted`)) : null,
    capabilities.accountCosts ? load("FinOps", () => authorizedJSON<FinOpsReport>(session, "finops",
      `${serviceConfig.finops}/api/v1/finops/aws/report`)) : null,
  ]);
  if (telemetry) errors.push(...telemetry.errors);
  const amount = report?.summary?.total_actual_monthly_cost;
  const currency = report?.summary?.currency;

  return {
    metrics: {
      projects: projects?.data?.length ?? null,
      infrastructure: infrastructure?.items?.length ?? null,
      deployments: deployments?.items?.length ?? null,
      incidents: incidents ? extractIncidentCount(incidents) : null,
    },
    projects: projects?.data ?? [],
    pendingApprovals: pending?.items?.length ?? null,
    accountCost: typeof amount === "number" && Number.isFinite(amount) && currency ? { amount, currency } : null,
    observability: telemetry?.observability ?? {
      availability: null, requestRate: null, errorRate: null, p95Latency: null,
      deploymentsInProgress: null, requestsInFlight: null,
    },
    errors: errors.sort((left, right) => left.localeCompare(right)),
  };
}
