export type IncidentStatus =
  | "open"
  | "acknowledged"
  | "assigned"
  | "resolved"
  | string;

export type IncidentSeverity =
  | "critical"
  | "warning"
  | "high"
  | "medium"
  | "low"
  | string;

export type IncidentPriority = "P1" | "P2" | "P3" | "P4" | string;

export interface Incident {
  id: string;
  fingerprint: string;
  alert_name: string;
  service: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  impact: string;
  confidence: string;
  analysis_version: string;
  priority: IncidentPriority;
  summary: string;
  probable_cause: string;
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
  raw_alerts: RawAlert[];
}

export interface RawAlert {
  endsAt: string | null;
  labels: Record<string, string>;
  status: string;
  startsAt: string | null;
  annotations: Record<string, string>;
  generatorURL: string | null;
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

export interface IncidentTimelineEvent {
  id: string;
  incident_id: string;
  event_type: string;
  message: string;
  status?: string | null;
  actor: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface IncidentTimelineResponse {
  events?: IncidentTimelineEvent[];
  items?: IncidentTimelineEvent[];
  data?: IncidentTimelineEvent[];
}
