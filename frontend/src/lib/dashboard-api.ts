import { serviceConfig } from "@/lib/config";
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

async function requestJson<T>(
  url: string,
): Promise<T> {
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    throw new Error(
      `Request failed with status ${response.status}`,
    );
  }

  return response.json() as Promise<T>;
}

async function getCount<T>(
  url: string,
  extractCount: (data: T) => number,
): Promise<number> {
  const data = await requestJson<T>(url);

  return extractCount(data);
}

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
): number {
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

  return 0;
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

export async function getDashboardData(): Promise<DashboardData> {
  const errors: string[] = [];

  const results = await Promise.allSettled([
    getCount<ProjectListResponse>(
      `${serviceConfig.project}/projects?limit=100&offset=0`,
      (data) => data.count ?? data.data.length,
    ),

    getCount<InfrastructureListResponse>(
      `${serviceConfig.infrastructure}/api/v1/resources?limit=100&offset=0`,
      (data) => data.items.length,
    ),

    getCount<DeploymentListResponse>(
      `${serviceConfig.deployment}/api/v1/deployments?limit=100&offset=0`,
      (data) => data.items.length,
    ),

    getCount<IncidentListResponse>(
      `${serviceConfig.aiops}/api/v1/incidents?limit=100&offset=0`,
      extractIncidentCount,
    ),

    getObservabilityData(),
  ]);

  const serviceNames = [
    "projects",
    "infrastructure",
    "deployments",
    "incidents",
    "observability",
  ];

  const values = results.map((result, index) => {
    if (result.status === "fulfilled") {
      return result.value;
    }

    errors.push(
      `Unable to load ${serviceNames[index]} data`,
    );

    return 0;
  });

  const observabilityResult = values[4];

  const observability: DashboardObservability =
    typeof observabilityResult === "object" &&
    observabilityResult !== null &&
    "observability" in observabilityResult
      ? observabilityResult.observability
      : {
          availability: null,
          requestRate: null,
          errorRate: null,
          p95Latency: null,
          deploymentsInProgress: null,
          requestsInFlight: null,
        };

  if (
    typeof observabilityResult === "object" &&
    observabilityResult !== null &&
    "errors" in observabilityResult &&
    Array.isArray(observabilityResult.errors)
  ) {
    errors.push(...observabilityResult.errors);
  }

  return {
    metrics: {
      projects: typeof values[0] === "number" ? values[0] : 0,
      infrastructure:
        typeof values[1] === "number" ? values[1] : 0,
      deployments:
        typeof values[2] === "number" ? values[2] : 0,
      incidents:
        typeof values[3] === "number" ? values[3] : 0,
    },
    observability,
    errors,
  };
}
