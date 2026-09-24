export type IncidentStatus =
  | "open"
  | "acknowledged"
  | "assigned"
  | "resolved";

export type IncidentSeverity =
  | "info"
  | "warning"
  | "critical";

export type IncidentImpact =
  | "unknown"
  | "low"
  | "medium"
  | "high"
  | "critical";

export type AnalysisConfidence =
  | "low"
  | "medium"
  | "high";

export interface DeploymentCorrelation {
  deployment_id: string;
  environment: string;
  status: string;
  image: string | null;
  git_commit_sha: string | null;
  namespace: string | null;
  deployment_created_at: string;
  deployment_updated_at: string;
  incident_time_difference_seconds: number;
  correlation_type: string;
  correlation_strength: string;
  explanation: string;
}

export interface AIAnalysis {
  status: string;
  provider: string;
  model: string | null;

  summary: string | null;
  probable_cause: string | null;

  root_cause_hints: string[];
  recommended_actions: string[];

  confidence: AnalysisConfidence | null;

  assessment: string | null;

  evidence: Record<string, number | null>;

  evidence_findings: string[];

  deployment_correlations: DeploymentCorrelation[];

  generated_at: string | null;

  error: string | null;
}

export interface Incident {
  id: string;
  fingerprint: string;
  alert_name: string;
  service: string;

  severity: IncidentSeverity;
  status: IncidentStatus;
  impact: IncidentImpact;
  confidence: AnalysisConfidence;

  analysis_version: string;
  priority: string;

  summary: string;
  probable_cause: string | null;

  root_cause_hints: string[];
  recommended_actions: string[];

  labels: Record<string, string>;
  annotations: Record<string, string>;

  created_at: string;
  updated_at: string;

  acknowledged_at: string | null;
  acknowledged_by: string | null;

  assigned_to: string | null;
  assigned_at: string | null;

  resolved_at: string | null;
  resolved_by: string | null;
  resolution_notes: string | null;

  alert_count: number;

  raw_alerts: Record<string, unknown>[];

  ai_analysis: AIAnalysis | null;
}

export interface IncidentTimelineEvent {
  id: number;
  incident_id: string;
  event_type: string;
  message: string;
  status: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface IncidentTimelineResponse {
  incident_id: string;
  count: number;
  events: IncidentTimelineEvent[];
}

export interface IncidentListResponse {
  count: number;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  incidents: Incident[];
}

export interface IncidentStats {
  total_incidents: number;
  open_incidents: number;
  resolved_incidents: number;
  total_alerts: number;
  average_alerts_per_incident: number;
  incidents_by_priority: Record<string, number>;
  incidents_by_impact: Record<string, number>;
  incidents_by_service: Record<string, number>;
}
