export interface ApiError {
  message: string;
  code?: string;
  details?: unknown;
}

export interface Pagination {
  limit: number;
  offset: number;
  count?: number;
}

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  repository_url: string;
  default_branch: string;
  status: "active" | "inactive" | "archived";
  created_at: string;
  updated_at: string;
}

export interface CreateProjectInput {
  name: string;
  description?: string;
  repository_url: string;
  default_branch: string;
}

export interface UpdateProjectInput {
  name?: string;
  description?: string | null;
  repository_url?: string;
  default_branch?: string;
  status?: "active" | "inactive" | "archived";
}

export interface ProjectListResponse {
  data: Project[];
  limit: number;
  offset: number;
  count: number;
}

export type InfrastructureProvider =
  | "aws"
  | "azure"
  | "gcp"
  | "local";

export type InfrastructureStatus =
  | "active"
  | "inactive"
  | "provisioning"
  | "destroying"
  | "failed";

export interface InfrastructureResource {
  id: string;
  name: string;
  description?: string | null;
  provider: InfrastructureProvider;
  region: string;
  environment: string;
  status: InfrastructureStatus;
  terraform_directory: string;
  created_at: string;
  updated_at: string;
}

export interface CreateInfrastructureInput {
  name: string;
  description?: string;
  provider: InfrastructureProvider;
  region: string;
  environment: string;
  terraform_directory: string;
}

export interface UpdateInfrastructureInput {
  name?: string;
  description?: string | null;
  provider?: InfrastructureProvider;
  region?: string;
  environment?: string;
  status?: InfrastructureStatus;
  terraform_directory?: string;
}

export interface InfrastructureListResponse {
  items: InfrastructureResource[];
  limit: number;
  offset: number;
}

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
  duration_seconds?: number | null;
}

export interface DeploymentListResponse {
  items: Deployment[];
  limit: number;
  offset: number;
}
