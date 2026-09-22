export type ProjectStatus =
  | "active"
  | "inactive"
  | "archived";

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  repository_url: string;
  default_branch: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  data: Project[];
  limit: number;
  offset: number;
  count: number;
}

export interface CreateProjectInput {
  name: string;
  description?: string;
  repository_url: string;
  default_branch: string;
}

export interface UpdateProjectInput {
  name?: string;
  description?: string;
  repository_url?: string;
  default_branch?: string;
  status?: ProjectStatus;
}
