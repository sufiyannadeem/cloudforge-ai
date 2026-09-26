import type { AnomalySummary } from "@/types/anomaly";

export async function getAnomalySummary(
  service = "deployment-service",
  windowMinutes = 60,
  stepSeconds = 60,
): Promise<AnomalySummary> {
  const params = new URLSearchParams({
    service,
    window_minutes: String(windowMinutes),
    step_seconds: String(stepSeconds),
  });

  const response = await fetch(
    `/api/anomalies/summary?${params.toString()}`,
    {
      method: "GET",
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const message = await response.text();

    throw new Error(
      message || `Anomaly request failed with ${response.status}`,
    );
  }

  return (await response.json()) as AnomalySummary;
}
