export interface DashboardMetrics {
  projects: number;
  infrastructure: number;
  deployments: number;
  incidents: number;
}

export interface DashboardData {
  metrics: DashboardMetrics;
  errors: string[];
}
