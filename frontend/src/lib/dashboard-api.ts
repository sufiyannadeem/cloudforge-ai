import { serviceConfig } from "@/lib/config";
import type {
  DeploymentListResponse,
  InfrastructureListResponse,
  ProjectListResponse,
} from "@/types/api";
import type { DashboardData } from "@/types/dashboard";

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

  if (Array.isArray(data.items)) {
    return data.items.length;
  }

  if (Array.isArray(data.data)) {
    return data.data.length;
  }

  return 0;
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
  ]);

  const serviceNames = [
    "projects",
    "infrastructure",
    "deployments",
    "incidents",
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

  return {
    metrics: {
      projects: values[0],
      infrastructure: values[1],
      deployments: values[2],
      incidents: values[3],
    },
    errors,
  };
}
