export type DeploymentStatus =
  | "pending"
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type DeploymentAttemptStatus =
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface Deployment {
  id: string;
  project_id: string;
  environment: string;
  image: string;
  git_commit_sha: string;
  namespace: string;
  status: DeploymentStatus;
  execution_mode?: "simulated" | "kubernetes" | "unknown";
  created_at: string;
  updated_at: string;
}

export interface DeploymentAttempt {
  id: string;
  deployment_id: string;
  attempt_number: number;
  status: DeploymentAttemptStatus;
  execution_mode?: "simulated" | "kubernetes" | "unknown";
  error_message?: string | null;
  started_at: string;
  completed_at?: string | null;
  duration_ms?: number | null;
  created_at: string;
}

export interface DeploymentListResponse {
  count: number;
  data: Deployment[];
  limit: number;
  offset: number;
}

export interface DiagnosticCapture {
  id: string;
  actor: string;
  captured_at: string;
  evidence: {
    source: "live_kubernetes";
    observed_at: string;
    desired_replicas: number | null;
    available_replicas: number | null;
    severity: "insufficient_data" | "info" | "warning" | "high";
    likely_cause: string;
    recommendation: string;
    sample: {
      name: string;
      phase: string;
      ready: boolean | null;
      restarts: number | null;
      reasons: string[];
      events_checked: boolean;
      logs_checked: boolean;
      log_error_signal: boolean;
      usage: { cpu: string; memory: string; timestamp: string } | null;
    } | null;
  };
}
