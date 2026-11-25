import { frontendApiRequest } from "@/lib/frontend-api";

import type {
  Incident,
  IncidentListResponse,
  IncidentStats,
  IncidentTimelineEvent,
  AIAnalysis,
  RemediationProposal,
  RemediationResponse,
  RemediationAction,
} from "@/types/incidents";

const REQUEST_TIMEOUT_MS = 10_000;

async function requestJson<T>(
  url: string,
  options: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<T> {
  return frontendApiRequest<T>(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
    signal: options.signal ?? AbortSignal.timeout(timeoutMs),
  });
}

const incidentsBaseUrl =
  "/api/proxy/aiops/api/v1/incidents";

export async function getIncidents(
  params: Record<string, string | number | undefined> = {},
): Promise<IncidentListResponse> {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      searchParams.set(key, String(value));
    }
  }

  const query = searchParams.toString();

  return requestJson<IncidentListResponse>(
    `${incidentsBaseUrl}${query ? `?${query}` : ""}`,
  );
}

export async function getIncident(
  incidentId: string,
): Promise<Incident> {
  return requestJson<Incident>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}`,
  );
}

export async function getIncidentTimeline(
  incidentId: string,
): Promise<IncidentTimelineEvent[]> {
  const response =
    await requestJson<{
      incident_id: string;
      count: number;
      events: IncidentTimelineEvent[];
    }>(
      `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/timeline`,
    );

  return response.events;
}

export async function getIncidentAIAnalysis(
  incidentId: string,
): Promise<AIAnalysis | null> {
  const response =
    await requestJson<{
      incident_id: string;
      ai_analysis: AIAnalysis | null;
    }>(
      `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/ai-analysis`,
    );

  return response.ai_analysis;
}

export async function analyzeIncident(
  incidentId: string,
): Promise<{
  incident: Incident;
  ai_analysis: AIAnalysis | null;
}> {
  return requestJson(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/analyze`,
    {
      method: "POST",
    },
    25_000,
  );
}

export async function analyzeIncidentDeterministic(
  incidentId: string,
): Promise<{
  incident: Incident;
  ai_analysis: AIAnalysis | null;
}> {
  return requestJson(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/analyze/deterministic`,
    {
      method: "POST",
    },
  );
}

export async function getIncidentStats(): Promise<IncidentStats> {
  return requestJson<IncidentStats>(
    `${incidentsBaseUrl}/stats`,
  );
}

export async function acknowledgeIncident(
  incidentId: string,
  acknowledgedBy: string,
): Promise<Incident> {
  return requestJson<Incident>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/acknowledge`,
    {
      method: "PATCH",
      body: JSON.stringify({
        acknowledged_by: acknowledgedBy,
      }),
    },
  );
}

export async function assignIncident(
  incidentId: string,
  assignedTo: string,
): Promise<Incident> {
  return requestJson<Incident>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/assign`,
    {
      method: "PATCH",
      body: JSON.stringify({
        assigned_to: assignedTo,
      }),
    },
  );
}

export async function unassignIncident(
  incidentId: string,
): Promise<Incident> {
  return requestJson<Incident>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/assign`,
    {
      method: "DELETE",
    },
  );
}

export async function resolveIncident(
  incidentId: string,
  resolutionNotes: string,
  resolvedBy: string,
): Promise<Incident> {
  return requestJson<Incident>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/resolve`,
    {
      method: "PATCH",
      body: JSON.stringify({
        resolved_by: resolvedBy,
        resolution_notes: resolutionNotes,
      }),
    },
  );
}


export async function getIncidentRemediation(
  incidentId: string,
): Promise<RemediationResponse> {
  return requestJson<RemediationResponse>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/remediation`,
  );
}

export async function previewIncidentRemediation(
  incidentId: string,
  payload: {
    action: RemediationAction;
    target_deployment_id?: string;
    reason?: string;
    requested_by: string;
  },
): Promise<RemediationProposal> {
  return requestJson<RemediationProposal>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/remediation/preview`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function approveIncidentRemediation(
  incidentId: string,
  proposalId: string,
  approvedBy: string,
  expectedVersion: number,
  expectedFingerprint: string,
): Promise<RemediationProposal> {
  return requestJson<RemediationProposal>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/remediation/${encodeURIComponent(proposalId)}/approve`,
    {
      method: "POST",
      body: JSON.stringify({
        approved_by: approvedBy,
        expected_version: expectedVersion,
        expected_fingerprint: expectedFingerprint,
      }),
    },
  );
}

export async function rejectIncidentRemediation(
  incidentId: string,
  proposalId: string,
  rejectedBy: string,
  reason?: string,
): Promise<RemediationProposal> {
  return requestJson<RemediationProposal>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/remediation/${encodeURIComponent(proposalId)}/reject`,
    {
      method: "POST",
      body: JSON.stringify({
        rejected_by: rejectedBy,
        reason,
      }),
    },
  );
}

export async function executeIncidentRemediation(
  incidentId: string,
  proposalId: string,
  executedBy: string,
  idempotencyKey: string,
): Promise<RemediationProposal> {
  return requestJson<RemediationProposal>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/remediation/${encodeURIComponent(proposalId)}/execute`,
    {
      method: "POST",
      body: JSON.stringify({
        executed_by: executedBy,
        idempotency_key: idempotencyKey,
      }),
    },
  );
}


export type RemediationReviewEvent = { id: number; proposal_id: string | null; effect?: string | null; recommendation_version: number; event_type: string; actor: string; reason: string | null; created_at: string };
export function getRemediationHistory(incidentId: string) {
  return requestJson<{incident_id: string; history: RemediationReviewEvent[]}>(`${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/remediation/history`);
}
export function requestRemediationAlternative(incidentId: string, proposalId: string) {
  return requestJson<{outcome: string; proposal_id: string | null; kind?: string; evidence_snapshot_only?: boolean; guidance?: string}>(`${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/remediation/${encodeURIComponent(proposalId)}/alternative`, {method: "POST"});
}
