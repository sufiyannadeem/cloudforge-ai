export type ServiceHealthStatus =
  | "healthy"
  | "unhealthy"
  | "not-checked";

export interface ServiceHealth {
  name: string;
  description: string;
  port: number;
  status: ServiceHealthStatus;
  latencyMs: number | null;
  error?: string;
}

export interface HealthCheckResponse {
  checkedAt: string;
  healthyCount: number;
  totalCount: number;
  services: ServiceHealth[];
}
