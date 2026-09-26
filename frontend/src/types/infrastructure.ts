export type InfrastructureStatus =
  | "pending"
  | "provisioning"
  | "active"
  | "failed"
  | "destroyed";

export interface InfrastructureResource {
  id: string;
  project_id: string;
  name: string;
  resource_type: string;
  provider: string;
  region: string;
  environment: string;
  configuration: Record<string, unknown>;
  status: InfrastructureStatus;
  created_at: string;
  updated_at: string;
}

export interface InfrastructureListResponse {
  count: number;
  data: InfrastructureResource[];
  limit: number;
  offset: number;
}

export interface InfrastructureFormData {
  project_id: string;
  name: string;
  resource_type: string;
  provider: string;
  region: string;
  configuration: string;
}
