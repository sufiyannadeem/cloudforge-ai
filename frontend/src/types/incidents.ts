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


export type RemediationAction =
  | "acknowledge_incident"
  | "no_action"
  | "rerun_deployment"
  | "restart_deployment"
  | "scale_deployment"
  | "rollback_deployment";

export type RemediationStatus =
  | "PROPOSED"
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "EXECUTING"
  | "SUCCEEDED"
  | "FAILED";

export type RemediationPolicyDecision =
  | "allowed"
  | "blocked"
  | "requires_approval";

export interface RemediationAvailableAction {
  action: RemediationAction;
  policy: RemediationPolicyDecision;
  human_approval_required: boolean;
  description: string;
}

export interface RemediationProposal {
  id: string;
  incident_id: string;
  action: RemediationAction;
  status: RemediationStatus;
  policy_decision: RemediationPolicyDecision;
  policy_reason: string;
  reason: string | null;
  target_deployment_id: string | null;
  proposed_by: string;
  approved_by: string | null;
  rejected_by: string | null;
  rejection_reason: string | null;
  execution_requested_by: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  rejected_at: string | null;
  executed_at: string | null;
}

export interface RemediationResponse {
  incident_id: string;
  available_actions: RemediationAvailableAction[];
  proposals: RemediationProposal[];
}
