export type InfrastructureStatus =
  | "pending"
  | "planning"
  | "awaiting_approval"
  | "provisioning"
  | "active"
  | "inactive"
  | "destroying"
  | "awaiting_destroy_approval"
  | "failed"
  | "destroyed";

export interface InfrastructureResource {
  id: string;
  project_id: string | null;
  name: string;
  description?: string | null;
  resource_type: string;
  provider: string;
  region: string;
  environment: string;
  configuration: Record<string, unknown>;
  status: InfrastructureStatus;
  terraform_directory?: string | null;
  plan_path?: string | null;
  plan_hash?: string | null;
  plan_created_at?: string | null;
  plan_summary?: string | null;
  destroy_plan_path?: string | null;
  destroy_plan_hash?: string | null;
  approval_expires_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlanDetails {
  resource_id: string;
  resource_name: string;
  resource_type: string;
  provider: string;
  region: string;
  environment: string;
  status: InfrastructureStatus;
  plan_hash: string;
  plan_created_at?: string | null;
  approval_expires_at?: string | null;
  is_expired: boolean;
  plan_summary: string;
  configuration: Record<string, unknown>;
}

export interface InfrastructureListResponse {
  count?: number;
  items?: InfrastructureResource[];
  data?: InfrastructureResource[];
  limit?: number;
  offset?: number;
}

export interface InfrastructureFormData {
  project_id: string;
  name: string;
  resource_type: string;
  provider: string;
  region: string;
  environment: string;
  configuration: string;
}

export interface ApplyResourceInput {
  plan_hash: string;
}
