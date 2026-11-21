import type { Project } from "@/types/api";

export interface DashboardMetrics {
  projects: number | null;
  infrastructure: number | null;
  deployments: number | null;
  incidents: number | null;
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
  projects: Project[];
  pendingApprovals: number | null;
  accountCost: { amount: number; currency: string } | null;
}
