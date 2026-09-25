import type {
  PrometheusQueryResponse,
  PrometheusSample,
} from "@/types/observability";

const PROMETHEUS_URL =
  process.env.PROMETHEUS_URL ??
  "http://localhost:9090";

const REQUEST_TIMEOUT_MS = 10_000;

function isServer(): boolean {
  return typeof window === "undefined";
}

function buildQueryURL(query: string): string {
  if (!isServer()) {
    const url = new URL(
      "/api/observability",
      window.location.origin,
    );

    url.searchParams.set("query", query);

    return url.toString();
  }

  const url = new URL(
    "/api/v1/query",
    PROMETHEUS_URL,
  );

  url.searchParams.set("query", query);

  return url.toString();
}

async function queryPrometheus(
  query: string,
): Promise<PrometheusQueryResponse> {
  const controller = new AbortController();

  const timeout = setTimeout(() => {
    controller.abort();
  }, REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(
      buildQueryURL(query),
      {
        method: "GET",
        cache: "no-store",
        signal: controller.signal,
      },
    );

    if (!response.ok) {
      throw new Error(
        `Prometheus query failed with ${response.status}`,
      );
    }

    return (await response.json()) as PrometheusQueryResponse;
  } finally {
    clearTimeout(timeout);
  }
}

function firstValue(
  response: PrometheusQueryResponse,
): number | null {
  const sample = response.data?.result?.[0];

  if (!sample) {
    return null;
  }

  const value = Array.isArray(sample.value)
    ? sample.value[1]
    : undefined;

  if (value === undefined) {
    return null;
  }

  const parsed = Number(value);

  return Number.isFinite(parsed) ? parsed : null;
}

async function getMetric(
  query: string,
): Promise<number | null> {
  try {
    const response = await queryPrometheus(query);

    return firstValue(response);
  } catch {
    return null;
  }
}

export async function getServiceAvailability(): Promise<
  number | null
> {
  return getMetric(
    'cloudforge:service_availability:percent{job="deployment-service"}',
  );
}

export async function getRequestRate(): Promise<
  number | null
> {
  return getMetric(
    'cloudforge:http_request_rate:5m{job="deployment-service"}',
  );
}

export async function getErrorRate(): Promise<
  number | null
> {
  return getMetric(
    'cloudforge:http_error_rate:percent:5m{job="deployment-service"}',
  );
}

export async function getP95Latency(): Promise<
  number | null
> {
  return getMetric(
    'cloudforge:http_request_latency_p95_ms:5m{job="deployment-service"}',
  );
}

export async function getDeploymentProgress(): Promise<
  number | null
> {
  return getMetric(
    "cloudforge:deployments_in_progress",
  );
}

export async function getRequestsInFlight(): Promise<
  number | null
> {
  return getMetric(
    "cloudforge:http_requests_in_flight",
  );
}

export async function getPrometheusSamples(
  query: string,
): Promise<PrometheusSample[]> {
  try {
    const response = await queryPrometheus(query);

    return response.data?.result ?? [];
  } catch {
    return [];
  }
}
