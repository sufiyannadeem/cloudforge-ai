"use client";

import type { IncidentTimelineEvent } from "@/types/incidents";

interface IncidentTimelineProps {
  events: IncidentTimelineEvent[];
  formatDate: (value: string) => string;
  badgeClass: (value: string) => string;
}

function formatEventType(eventType: string): string {
  const labels: Record<string, string> = {
    created: "Incident Created",
    acknowledged: "Incident Acknowledged",
    assigned: "Incident Assigned",
    reassigned: "Incident Reassigned",
    unassigned: "Incident Unassigned",
    ai_analysis: "AI Analysis",
    resolved: "Incident Resolved",
  };

  return (
    labels[eventType] ??
    eventType
      .replace(/_/g, " ")
      .replace(/\b\w/g, (character) =>
        character.toUpperCase(),
      )
  );
}

function eventTone(eventType: string): string {
  switch (eventType) {
    case "created":
      return "bg-blue-600";

    case "acknowledged":
      return "bg-yellow-500";

    case "assigned":
    case "reassigned":
      return "bg-purple-600";

    case "unassigned":
      return "bg-gray-500";

    case "ai_analysis":
      return "bg-indigo-600";

    case "resolved":
      return "bg-green-600";

    default:
      return "bg-gray-500";
  }
}

function eventBadgeClass(eventType: string): string {
  switch (eventType) {
    case "created":
      return "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300";

    case "acknowledged":
      return "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300";

    case "assigned":
    case "reassigned":
      return "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300";

    case "unassigned":
      return "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300";

    case "ai_analysis":
      return "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300";

    case "resolved":
      return "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300";

    default:
      return "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300";
  }
}

function metadataString(
  metadata: Record<string, unknown>,
  key: string,
): string | null {
  const value = metadata[key];

  return typeof value === "string" && value.length > 0
    ? value
    : null;
}

function metadataNumber(
  metadata: Record<string, unknown>,
  key: string,
): number | null {
  const value = metadata[key];

  return typeof value === "number" &&
    Number.isFinite(value)
    ? value
    : null;
}

function renderAssignmentMetadata(
  event: IncidentTimelineEvent,
) {
  const assignedTo = metadataString(
    event.metadata,
    "assigned_to",
  );

  const previousAssignee = metadataString(
    event.metadata,
    "previous_assignee",
  );

  if (!assignedTo && !previousAssignee) {
    return null;
  }

  return (
    <div className="mt-3 rounded-lg border border-purple-200 bg-purple-50 p-3 dark:border-purple-900/60 dark:bg-purple-950/20">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-purple-700 dark:text-purple-300">
        Assignment Change
      </div>

      <div className="grid gap-2 text-sm sm:grid-cols-2">
        {previousAssignee && (
          <div>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Previous assignee
            </span>

            <div className="font-medium text-gray-900 dark:text-white">
              {previousAssignee}
            </div>
          </div>
        )}

        {assignedTo && (
          <div>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Assigned to
            </span>

            <div className="font-medium text-gray-900 dark:text-white">
              {assignedTo}
            </div>
          </div>
        )}

        {!assignedTo && previousAssignee && (
          <div>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Current assignee
            </span>

            <div className="font-medium text-gray-900 dark:text-white">
              Unassigned
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function renderAIAnalysisMetadata(
  event: IncidentTimelineEvent,
) {
  const assessment = metadataString(
    event.metadata,
    "assessment",
  );

  const confidence = metadataString(
    event.metadata,
    "confidence",
  );

  const provider = metadataString(
    event.metadata,
    "provider",
  );

  const model = metadataString(
    event.metadata,
    "model",
  );

  const aiStatus = metadataString(
    event.metadata,
    "ai_status",
  );

  const error = metadataString(
    event.metadata,
    "error",
  );

  const evidenceFields =
    Array.isArray(
      event.metadata.evidence_fields,
    )
      ? event.metadata.evidence_fields.filter(
          (value): value is string =>
            typeof value === "string",
        )
      : [];

  return (
    <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 dark:border-indigo-900/60 dark:bg-indigo-950/20">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-300">
          AI Analysis Metadata
        </span>

        {aiStatus && (
          <span
            className={`rounded-full px-2 py-1 text-xs font-medium ${
              aiStatus === "ai_generated"
                ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"
                : aiStatus === "fallback"
                  ? "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300"
                  : "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300"
            }`}
          >
            {aiStatus}
          </span>
        )}
      </div>

      <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        {provider && (
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Provider
            </div>

            <div className="font-medium text-gray-900 dark:text-white">
              {provider}
            </div>
          </div>
        )}

        {model && (
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Model
            </div>

            <div className="break-all font-medium text-gray-900 dark:text-white">
              {model}
            </div>
          </div>
        )}

        {assessment && (
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Assessment
            </div>

            <div className="font-medium text-gray-900 dark:text-white">
              {assessment}
            </div>
          </div>
        )}

        {confidence && (
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Confidence
            </div>

            <div className="font-medium text-gray-900 dark:text-white">
              {confidence}
            </div>
          </div>
        )}
      </div>

      {evidenceFields.length > 0 && (
        <div className="mt-3">
          <div className="mb-2 text-xs text-gray-500 dark:text-gray-400">
            Evidence fields
          </div>

          <div className="flex flex-wrap gap-2">
            {evidenceFields.map((field) => (
              <span
                key={field}
                className="rounded-md bg-white px-2 py-1 text-xs text-gray-700 shadow-sm dark:bg-gray-900 dark:text-gray-300"
              >
                {field}
              </span>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="mt-3 rounded-md border border-orange-200 bg-orange-50 p-3 text-xs text-orange-800 dark:border-orange-900/60 dark:bg-orange-950/20 dark:text-orange-300">
          <div className="font-semibold">
            AI analysis fallback
          </div>

          <div className="mt-1">
            {error}
          </div>
        </div>
      )}
    </div>
  );
}

function renderGenericMetadata(
  event: IncidentTimelineEvent,
) {
  const entries = Object.entries(
    event.metadata,
  ).filter(
    ([key]) =>
      ![
        "assigned_to",
        "previous_assignee",
        "assessment",
        "confidence",
        "provider",
        "model",
        "ai_status",
        "error",
        "evidence_fields",
      ].includes(key),
  );

  if (entries.length === 0) {
    return null;
  }

  return (
    <details className="mt-3 rounded-lg bg-gray-50 p-3 dark:bg-gray-800">
      <summary className="cursor-pointer text-xs font-semibold text-gray-600 dark:text-gray-300">
        Event metadata
      </summary>

      <div className="mt-3 space-y-2">
        {entries.map(([key, value]) => (
          <div
            key={key}
            className="grid gap-1 text-xs sm:grid-cols-[180px_1fr]"
          >
            <span className="font-medium text-gray-500 dark:text-gray-400">
              {key}
            </span>

            <span className="break-words text-gray-700 dark:text-gray-300">
              {typeof value === "object"
                ? JSON.stringify(value)
                : String(value)}
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}

function renderEventDetails(
  event: IncidentTimelineEvent,
) {
  if (
    event.event_type === "assigned" ||
    event.event_type === "reassigned" ||
    event.event_type === "unassigned"
  ) {
    return renderAssignmentMetadata(event);
  }

  if (event.event_type === "ai_analysis") {
    return (
      <>
        {renderAIAnalysisMetadata(event)}

        {renderGenericMetadata(event)}
      </>
    );
  }

  return renderGenericMetadata(event);
}

export default function IncidentTimeline({
  events,
  formatDate,
  badgeClass,
}: IncidentTimelineProps) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        No timeline events available.
      </p>
    );
  }

  return (
    <div className="relative">
      <div className="absolute bottom-0 left-[7px] top-0 w-px bg-gray-200 dark:bg-gray-700" />

      <div className="space-y-6">
        {events.map((event, index) => (
          <div
            key={event.id}
            className="relative pl-8"
          >
            <div
              className={`absolute left-0 top-1.5 h-4 w-4 rounded-full border-2 border-white shadow-sm dark:border-gray-900 ${eventTone(
                event.event_type,
              )}`}
            />

            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium text-gray-400 dark:text-gray-500">
                      #{index + 1}
                    </span>

                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${eventBadgeClass(
                        event.event_type,
                      )}`}
                    >
                      {formatEventType(
                        event.event_type,
                      )}
                    </span>

                    {event.status && (
                      <span
                        className={`rounded-full px-2 py-1 text-xs ${badgeClass(
                          event.status,
                        )}`}
                      >
                        {event.status}
                      </span>
                    )}
                  </div>
                </div>

                <span className="shrink-0 text-xs text-gray-500 dark:text-gray-400">
                  {formatDate(
                    event.created_at,
                  )}
                </span>
              </div>

              <p className="mt-3 text-sm leading-6 text-gray-700 dark:text-gray-300">
                {event.message}
              </p>

              {renderEventDetails(event)}

              {event.event_type === "ai_analysis" &&
                metadataNumber(
                  event.metadata,
                  "correlation_count",
                ) !== null && (
                  <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                    Deployment correlations:{" "}
                    {metadataNumber(
                      event.metadata,
                      "correlation_count",
                    )}
                  </div>
                )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
