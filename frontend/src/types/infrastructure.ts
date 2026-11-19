export type InfrastructureStatus =
  | "pending"
  | "planning"
  | "awaiting_approval"
  | "provisioning"
  | "active"
  | "inactive"
  | "destroying"
  | "destroy_failed"
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
  terraform_resource_id?: string;
  aws_last_verified_at?: string;
  last_execution_error?: string;
  status_source?: "terraform_workflow";
  aws_live_status?: "unverified";
  terraform_directory?: string | null;
  plan_path?: string | null;
  plan_hash?: string | null;
  plan_created_at?: string | null;
  plan_summary?: string | null;
  destroy_plan_path?: string | null;
  destroy_plan_hash?: string | null;
  approval_expires_at?: string | null;
  requested_by?: string;
  destroy_requested_by?: string;
  review_status?: string;
  created_at: string;
  updated_at: string;
}

export interface PlanReview {
  operation: "apply" | "destroy";
  revision: string;
  plan_hash: string;
  status: string;
  requester: string;
  submitted_by: string;
  submitted_at: string;
  decided_by?: string;
  decided_at?: string;
  executed_by?: string;
  execution_started_at?: string;
  finished_at?: string;
}

export interface PlanPricingBasis {
  resource_type: "aws_instance" | "aws_db_instance" | "aws_eks_node_group";
  unit: string;
  quantity: number;
}

export interface PlanDetails {
  pricing_basis?: PlanPricingBasis;
  project_id?: string;
  requester?: string;
  revision: string;
  operation: "apply" | "destroy";
  reviews: PlanReview[] | null;
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
  configuration: Record<string, string | boolean>;
}

export interface ApplyResourceInput {
  plan_hash: string;
}

export type TerraformDriftScan = {
  id: number;
  scanned_at: string;
  status: "observed" | "unavailable";
  findings: { address?: string; type: string; source: string; severity: string; risk: string; recommendation: string }[] | null;
};
