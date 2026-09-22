import {
  Incident,
  IncidentListResponse,
  IncidentStats,
  IncidentTimelineEvent,
  IncidentTimelineResponse,
} from "@/types/incidents";

const INCIDENTS_BASE = "/api/proxy/aiops/api/v1/incidents";

async function request<T>(
  url: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(
      message || `Request failed with status ${response.status}`,
    );
  }

  return response.json() as Promise<T>;
}

export async function getIncidents(): Promise<Incident[]> {
  const result = await request<IncidentListResponse>(
    `${INCIDENTS_BASE}?limit=100&offset=0`,
  );

  return result.incidents ?? [];
}

export async function getIncident(
  incidentId: string,
): Promise<Incident> {
  return request<Incident>(`${INCIDENTS_BASE}/${incidentId}`);
}

export async function getIncidentTimeline(
  incidentId: string,
): Promise<IncidentTimelineEvent[]> {
  const result = await request<IncidentTimelineResponse>(
    `${INCIDENTS_BASE}/${incidentId}/timeline`,
  );

  return result.events ?? result.items ?? result.data ?? [];
}

export async function getIncidentStats(): Promise<IncidentStats> {
  return request<IncidentStats>(`${INCIDENTS_BASE}/stats`);
}

export async function acknowledgeIncident(
  incidentId: string,
  acknowledgedBy: string,
): Promise<Incident> {
  return request<Incident>(
    `${INCIDENTS_BASE}/${incidentId}/acknowledge`,
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
  return request<Incident>(
    `${INCIDENTS_BASE}/${incidentId}/assign`,
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
  return request<Incident>(
    `${INCIDENTS_BASE}/${incidentId}/unassign`,
    {
      method: "DELETE",
    },
  );
}

export async function resolveIncident(
  incidentId: string,
  resolutionNotes?: string,
): Promise<Incident> {
  return request<Incident>(
    `${INCIDENTS_BASE}/${incidentId}/resolve`,
    {
      method: "PATCH",
      body: JSON.stringify({
        resolved_by: "nadeem",
        resolution_notes: resolutionNotes ?? "",
      }),
    },
  );
}
