
import type {
  Incident,
  IncidentListResponse,
  IncidentStats,
  IncidentTimelineEvent,
  AIAnalysis,
} from "@/types/incidents";

const REQUEST_TIMEOUT_MS = 10_000;

async function requestJson<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    cache: "no-store",
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;

    try {
      const body = (await response.json()) as {
        detail?: string;
      };

      if (body.detail) {
        message = body.detail;
      }
    } catch {
      // Keep the generic HTTP error.
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
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
): Promise<Incident> {
  return requestJson<Incident>(
    `${incidentsBaseUrl}/${encodeURIComponent(incidentId)}/resolve`,
    {
      method: "PATCH",
      body: JSON.stringify({
        resolved_by: "nadeem",
        resolution_notes: resolutionNotes,
      }),
    },
  );
}
