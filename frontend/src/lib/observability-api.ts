import type {
  PrometheusQueryResponse,
  PrometheusSample,
} from "@/types/observability";

const PROMETHEUS_URL =
  process.env.PROMETHEUS_URL ?? "http://localhost:9090";

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

async function requestPrometheus(
  query: string,
): Promise<PrometheusQueryResponse> {
  const url = buildQueryURL(query);

  const response = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    const message = await response.text();

    throw new Error(
      message ||
        `Prometheus request failed with status ${response.status}`,
    );
  }

  const result =
    (await response.json()) as PrometheusQueryResponse;

  if (result.status !== "success") {
    throw new Error(
      result.error ||
        "Prometheus returned an unsuccessful response",
    );
  }

  return result;
}

export async function queryPrometheus(
  query: string,
): Promise<PrometheusSample[]> {
  const result = await requestPrometheus(query);

  if (!result.data || !Array.isArray(result.data.result)) {
    throw new Error(
      "Prometheus response did not contain valid metric data",
    );
  }

  return result.data.result;
}

function getNumericValue(
  samples: PrometheusSample[],
): number | null {
  const value = samples[0]?.value[1];

  if (value === undefined) {
    return null;
  }

  const numericValue = Number(value);

  return Number.isFinite(numericValue)
    ? numericValue
    : null;
}

export async function getDeploymentProgress(): Promise<
  number | null
> {
  const result = await queryPrometheus(
    "cloudforge_deployments_in_progress",
  );

  return getNumericValue(result);
}

export async function getRequestsInFlight(): Promise<
  number | null
> {
  const result = await queryPrometheus(
    "http_requests_in_flight",
  );

  return getNumericValue(result);
}

export async function getServiceAvailability(): Promise<
  number | null
> {
  const result = await queryPrometheus(
    'avg(up{job="deployment-service"}) * 100',
  );

  return getNumericValue(result);
}

export async function getRequestRate(): Promise<
  number | null
> {
  const result = await queryPrometheus(
    'sum(rate(http_requests_total{job="deployment-service"}[5m]))',
  );

  return getNumericValue(result);
}

export async function getErrorRate(): Promise<
  number | null
> {
  const result = await queryPrometheus(
    'sum(rate(http_requests_total{job="deployment-service",status=~"5.."}[5m])) / sum(rate(http_requests_total{job="deployment-service"}[5m])) * 100',
  );

  // No 5xx samples means the current error rate is zero.
  if (result.length === 0) {
    return 0;
  }

  return getNumericValue(result);
}

export async function getP95Latency(): Promise<
  number | null
> {
  const result = await queryPrometheus(
    'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="deployment-service"}[5m]))) * 1000',
  );

  return getNumericValue(result);
}
