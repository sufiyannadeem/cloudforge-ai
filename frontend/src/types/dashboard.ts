export interface DashboardMetrics {
  projects: number;
  infrastructure: number;
  deployments: number;
  incidents: number;
}

export interface DashboardObservability {
  availability: number | null;
  requestRate: number | null;
  errorRate: number | null;
  p95Latency: number | null;
  deploymentsInProgress: number | null;
  requestsInFlight: number | null;
}

export interface DashboardData {
  metrics: DashboardMetrics;
  observability: DashboardObservability;
  errors: string[];
}
