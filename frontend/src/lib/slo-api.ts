export type SLOStatus =
  | "healthy"
  | "at_risk"
  | "breached"
  | "insufficient_data";

export type SLOType =
  | "availability"
  | "error_rate"
  | "latency";

export interface SLOResult {
  name: string;
  description: string;
  service: string;
  type: SLOType;
  target: number;
  window: string;
  observed_value: number | null;
  compliance: number | null;
  error_budget_total: number | null;
  error_budget_consumed: number | null;
  error_budget_remaining: number | null;
  burn_rate: number | null;
  status: SLOStatus;
  sufficient_data: boolean;
  latency_threshold_ms: number | null;
  observed_at: string;
}

export interface SLOSummary {
  service: string;
  window: string;
  overall_status: SLOStatus;
  slo_count: number;
  healthy_count: number;
  at_risk_count: number;
  breached_count: number;
  insufficient_data_count: number;
  slos: SLOResult[];
  generated_at: string;
}

export type SLOBurnWindow =
  | "5m"
  | "30m"
  | "1h"
  | "6h";

export interface SLOBurnRates {
  availability: Record<SLOBurnWindow, number | null>;
  requestSuccess: Record<SLOBurnWindow, number | null>;
  latency: Record<SLOBurnWindow, number | null>;
  generatedAt: string;
}

async function queryPrometheusMetric(
  query: string,
): Promise<number | null> {
  const response = await fetch(
    `/api/observability?query=${encodeURIComponent(query)}`,
    {
      method: "GET",
      cache: "no-store",
    },
  );

  if (!response.ok) {
    return null;
  }

  const payload = (await response.json()) as {
    data?: {
      result?: Array<{
        value?: [number, string];
      }>;
    };
  };

  const value = payload.data?.result?.[0]?.value?.[1];

  if (value === undefined) {
    return null;
  }

  const parsed = Number(value);

  return Number.isFinite(parsed) ? parsed : null;
}

export async function getSLOSummary(
  service = "deployment-service",
): Promise<SLOSummary> {
  const response = await fetch(
    `/api/slo?service=${encodeURIComponent(service)}`,
    {
      method: "GET",
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const message = await response.text();

    throw new Error(
      message || `SLO request failed with ${response.status}`,
    );
  }

  return (await response.json()) as SLOSummary;
}

export async function getSLOBurnRates(): Promise<SLOBurnRates> {
  const windows: SLOBurnWindow[] = [
    "5m",
    "30m",
    "1h",
    "6h",
  ];

  const availability: Record<
    SLOBurnWindow,
    number | null
  > = {
    "5m": null,
    "30m": null,
    "1h": null,
    "6h": null,
  };

  const requestSuccess: Record<
    SLOBurnWindow,
    number | null
  > = {
    "5m": null,
    "30m": null,
    "1h": null,
    "6h": null,
  };

  const latency: Record<
    SLOBurnWindow,
    number | null
  > = {
    "5m": null,
    "30m": null,
    "1h": null,
    "6h": null,
  };

  await Promise.all(
    windows.flatMap((window) => [
      queryPrometheusMetric(
        `cloudforge:slo_availability_burn:${window}`,
      ).then((value) => {
        availability[window] = value;
      }),

      queryPrometheusMetric(
        `cloudforge:slo_request_success_burn:${window}`,
      ).then((value) => {
        requestSuccess[window] = value;
      }),

      queryPrometheusMetric(
        `cloudforge:slo_latency_burn:${window}`,
      ).then((value) => {
        latency[window] = value;
      }),
    ]),
  );

  return {
    availability,
    requestSuccess,
    latency,
    generatedAt: new Date().toISOString(),
  };
}
