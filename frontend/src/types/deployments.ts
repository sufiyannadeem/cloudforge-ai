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
  created_at: string;
  updated_at: string;
}

export interface DeploymentAttempt {
  id: string;
  deployment_id: string;
  attempt_number: number;
  status: DeploymentAttemptStatus;
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
