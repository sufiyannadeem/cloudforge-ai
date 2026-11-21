export const PLATFORM_SERVICES = ["project-service", "infrastructure-service", "deployment-service", "aiops-service", "finops-service", "frontend"] as const;
export type PlatformService = typeof PLATFORM_SERVICES[number];
export type ReliabilityMetric = "desired" | "available" | "hpaCurrent" | "hpaDesired" | "scalingLimited";
export interface ReliabilityRow { service: PlatformService; desired: number | null; available: number | null; hpaCurrent: number | null; hpaDesired: number | null; scalingLimited: number | null; }
const names = PLATFORM_SERVICES.join("|");
const fresh = (metric: string, label: string, extra = "") => {
  const selector = `${metric}{namespace="cloudforge",${label}=~"${names}"${extra}}`;
  return `max by (namespace, ${label}) (${selector} and (time() - timestamp(${selector}) < 60))`;
};
export const RELIABILITY_QUERIES: Record<ReliabilityMetric, { label: "deployment" | "horizontalpodautoscaler"; query: string }> = {
  desired: { label: "deployment", query: fresh("kube_deployment_spec_replicas", "deployment") },
  available: { label: "deployment", query: `${fresh("kube_deployment_status_replicas_available", "deployment")} and on(namespace, deployment) (${fresh("kube_deployment_status_observed_generation", "deployment")} == on(namespace, deployment) ${fresh("kube_deployment_metadata_generation", "deployment")})` },
  hpaCurrent: { label: "horizontalpodautoscaler", query: fresh("kube_horizontalpodautoscaler_status_current_replicas", "horizontalpodautoscaler") },
  hpaDesired: { label: "horizontalpodautoscaler", query: fresh("kube_horizontalpodautoscaler_status_desired_replicas", "horizontalpodautoscaler") },
  scalingLimited: { label: "horizontalpodautoscaler", query: fresh("kube_horizontalpodautoscaler_status_condition", "horizontalpodautoscaler", ',condition="ScalingLimited",status="true"') },
};

export function emptyReliability(): ReliabilityRow[] {
  return PLATFORM_SERVICES.map((service) => ({ service, desired: null, available: null, hpaCurrent: null, hpaDesired: null, scalingLimited: null }));
}

// Never coerce empty/error/stale/ambiguous results into measured zero or health.
export function reliabilityValues(body: unknown, label: "deployment" | "horizontalpodautoscaler", now = Date.now() / 1000): Map<string, number> {
  const values = new Map<string, number>();
  if (!body || typeof body !== "object") return values;
  const result = body as { status?: string; data?: { resultType?: string; result?: unknown } };
  if (result.status !== "success" || result.data?.resultType !== "vector" || !Array.isArray(result.data.result)) return values;
  const invalid = new Set<string>();
  for (const item of result.data.result) {
    if (!item || typeof item !== "object") continue;
    const sample = item as { metric?: Record<string, string>; value?: [number, string] };
    const service = sample.metric?.[label];
    if (sample.metric?.namespace !== "cloudforge" || !service || !PLATFORM_SERVICES.some((name) => name === service)) continue;
    if (!Array.isArray(sample.value) || sample.value.length !== 2) continue;
    const [timestamp, raw] = sample.value;
    if (typeof timestamp !== "number" || !Number.isFinite(timestamp) || timestamp > now + 5 || timestamp < now - 60 || typeof raw !== "string" || raw.trim() === "") continue;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0 || !Number.isSafeInteger(value)) continue;
    if (values.has(service) || invalid.has(service)) { values.delete(service); invalid.add(service); continue; }
    values.set(service, value);
  }
  return values;
}
