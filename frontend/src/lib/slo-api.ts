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
