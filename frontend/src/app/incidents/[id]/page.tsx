
"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

import AppShell from "@/components/layout/AppShell";
import {
  acknowledgeIncident,
  assignIncident,
  getIncident,
  getIncidentTimeline,
  resolveIncident,
  unassignIncident,
} from "@/lib/incidents-api";
import type {
  Incident,
  IncidentTimelineEvent,
} from "@/types/incidents";

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";

  return new Date(value).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function badgeClass(value: string): string {
  const normalized = value.toLowerCase();

  if (
    normalized === "critical" ||
    normalized === "p4" ||
    normalized === "failed"
  ) {
    return "bg-red-100 text-red-700";
  }

  if (
    normalized === "warning" ||
    normalized === "p2" ||
    normalized === "pending"
  ) {
    return "bg-yellow-100 text-yellow-700";
  }

  if (
    normalized === "resolved" ||
    normalized === "succeeded"
  ) {
    return "bg-green-100 text-green-700";
  }

  if (
    normalized === "acknowledged" ||
    normalized === "assigned" ||
    normalized === "running"
  ) {
    return "bg-blue-100 text-blue-700";
  }

  return "bg-gray-100 text-gray-700";
}

export default function IncidentDetailsPage() {
  const params = useParams<{ id: string }>();
  const incidentId = params.id;

  const [incident, setIncident] = useState<Incident | null>(null);
  const [timeline, setTimeline] = useState<IncidentTimelineEvent[]>([]);
  const [assignedTo, setAssignedTo] = useState("");
  const [resolutionNotes, setResolutionNotes] = useState("");

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const loadIncident = useCallback(async () => {
    try {
      setError("");

      const result = await getIncident(incidentId);

      setIncident(result);
      setAssignedTo(result.assigned_to ?? "");
      setResolutionNotes(result.resolution_notes ?? "");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load incident details.",
      );
    } finally {
      setLoading(false);
    }
  }, [incidentId]);

  const loadTimeline = useCallback(async () => {
    try {
      const events = await getIncidentTimeline(incidentId);
      setTimeline(events);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load incident timeline.",
      );
    }
  }, [incidentId]);

  const refreshDetails = useCallback(async () => {
    await Promise.all([loadIncident(), loadTimeline()]);
  }, [loadIncident, loadTimeline]);

  useEffect(() => {
    // Load incident details when the page mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshDetails();
  }, [refreshDetails]);

  function clearMessages() {
    setError("");
    setSuccessMessage("");
  }

  async function handleAcknowledge() {
    try {
      setActionLoading(true);
      clearMessages();

      await acknowledgeIncident(incidentId, "nadeem");
      await refreshDetails();

      setSuccessMessage("Incident acknowledged successfully.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Acknowledge action failed.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function handleAssign() {
    const username = assignedTo.trim();

    if (!username) {
      setError("Enter a user before assigning the incident.");
      setSuccessMessage("");
      return;
    }

    try {
      setActionLoading(true);
      clearMessages();

      await assignIncident(incidentId, username);
      await refreshDetails();

      setSuccessMessage(`Incident assigned to ${username}.`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Assignment action failed.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function handleUnassign() {
    try {
      setActionLoading(true);
      clearMessages();

      await unassignIncident(incidentId);
      await refreshDetails();

      setSuccessMessage("Incident unassigned successfully.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unassign action failed.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function handleResolve() {
    try {
      setActionLoading(true);
      clearMessages();

      await resolveIncident(incidentId, resolutionNotes);
      await refreshDetails();

      setSuccessMessage("Incident resolved successfully.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Resolve action failed.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) {
    return (
      <AppShell>
        <div className="p-8 text-gray-300">
          Loading incident details...
        </div>
      </AppShell>
    );
  }

  if (!incident) {
    return (
      <AppShell>
        <div className="p-8">
          <p className="text-red-400">
            {error || "Incident not found."}
          </p>

          <Link
            href="/incidents"
            className="mt-4 inline-block text-blue-400 hover:underline"
          >
            ← Back to incidents
          </Link>
        </div>
      </AppShell>
    );
  }

  const isResolved = incident.status.toLowerCase() === "resolved";
  const isAcknowledged = Boolean(incident.acknowledged_at);
  const isAssigned = Boolean(incident.assigned_to);

  return (
    <AppShell>
      <main className="min-w-0 space-y-6 bg-[#09090b] p-4 text-gray-100 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <Link
              href="/incidents"
              className="text-sm text-blue-400 hover:text-blue-300 hover:underline"
            >
              ← Back to incidents
            </Link>

            <p className="mt-4 text-sm font-medium text-blue-400">
              AIOps / Incident Intelligence
            </p>

            <h1 className="mt-2 break-words text-2xl font-bold text-white">
              {incident.alert_name}
            </h1>

            <p className="mt-2 break-all text-sm text-gray-400">
              {incident.id}
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              clearMessages();
              void refreshDetails();
            }}
            disabled={actionLoading}
            className="rounded-lg border border-gray-600 bg-gray-900 px-4 py-2 text-sm font-medium text-gray-200 transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Refresh
          </button>
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-lg border border-red-400/30 bg-red-950/50 p-4 text-sm text-red-300"
          >
            {error}
          </div>
        )}

        {successMessage && (
          <div
            role="status"
            className="rounded-lg border border-green-400/30 bg-green-950/40 p-4 text-sm text-green-300"
          >
            {successMessage}
          </div>
        )}

        <section className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <div className="rounded-xl bg-white p-5 shadow-sm">
            <p className="text-sm text-gray-500">Status</p>
            <span
              className={`mt-2 inline-block rounded-full px-3 py-1 text-sm font-semibold ${badgeClass(incident.status)}`}
            >
              {incident.status}
            </span>
          </div>

          <div className="rounded-xl bg-white p-5 shadow-sm">
            <p className="text-sm text-gray-500">Severity</p>
            <span
              className={`mt-2 inline-block rounded-full px-3 py-1 text-sm font-semibold ${badgeClass(incident.severity)}`}
            >
              {incident.severity}
            </span>
          </div>

          <div className="rounded-xl bg-white p-5 shadow-sm">
            <p className="text-sm text-gray-500">Priority</p>
            <span
              className={`mt-2 inline-block rounded-full px-3 py-1 text-sm font-semibold ${badgeClass(incident.priority)}`}
            >
              {incident.priority}
            </span>
          </div>

          <div className="rounded-xl bg-white p-5 shadow-sm">
            <p className="text-sm text-gray-500">Alert Count</p>
            <p className="mt-2 text-2xl font-bold text-gray-900">
              {incident.alert_count}
            </p>
          </div>
        </section>

        <section className="rounded-xl bg-white p-5 shadow-sm sm:p-6">
          <h2 className="text-lg font-semibold text-gray-900">
            Incident Overview
          </h2>

          <div className="mt-5 grid grid-cols-1 gap-5 md:grid-cols-2">
            <div>
              <p className="text-sm text-gray-500">Service</p>
              <p className="mt-1 break-words font-medium text-gray-900">
                {incident.service}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500">Impact</p>
              <p className="mt-1 font-medium capitalize text-gray-900">
                {incident.impact}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500">Confidence</p>
              <p className="mt-1 font-medium text-gray-900">
                {incident.confidence}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500">Analysis Version</p>
              <p className="mt-1 font-medium text-gray-900">
                {incident.analysis_version}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500">Created At</p>
              <p className="mt-1 font-medium text-gray-900">
                {formatDate(incident.created_at)}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500">Updated At</p>
              <p className="mt-1 font-medium text-gray-900">
                {formatDate(incident.updated_at)}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500">Acknowledged By</p>
              <p className="mt-1 font-medium text-gray-900">
                {incident.acknowledged_by || "—"}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500">Assigned To</p>
              <p className="mt-1 font-medium text-gray-900">
                {incident.assigned_to || "Unassigned"}
              </p>
            </div>

            {incident.resolved_by && (
              <div>
                <p className="text-sm text-gray-500">Resolved By</p>
                <p className="mt-1 font-medium text-gray-900">
                  {incident.resolved_by}
                </p>
              </div>
            )}

            {incident.resolved_at && (
              <div>
                <p className="text-sm text-gray-500">Resolved At</p>
                <p className="mt-1 font-medium text-gray-900">
                  {formatDate(incident.resolved_at)}
                </p>
              </div>
            )}
          </div>

          <div className="mt-6">
            <h3 className="font-semibold text-gray-900">Summary</h3>
            <p className="mt-2 break-words text-gray-600">
              {incident.summary}
            </p>
          </div>

          <div className="mt-6">
            <h3 className="font-semibold text-gray-900">
              Probable Cause
            </h3>
            <p className="mt-2 break-words text-gray-600">
              {incident.probable_cause || "No probable cause available."}
            </p>
          </div>

          {incident.resolution_notes && (
            <div className="mt-6">
              <h3 className="font-semibold text-gray-900">
                Resolution Notes
              </h3>
              <p className="mt-2 break-words text-gray-600">
                {incident.resolution_notes}
              </p>
            </div>
          )}
        </section>

        <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-xl bg-white p-5 shadow-sm sm:p-6">
            <h2 className="text-lg font-semibold text-gray-900">
              Root Cause Hints
            </h2>

            {incident.root_cause_hints.length === 0 ? (
              <p className="mt-4 text-sm text-gray-500">
                No root-cause hints available.
              </p>
            ) : (
              <ul className="mt-4 list-disc space-y-2 pl-5 text-gray-600">
                {incident.root_cause_hints.map((hint, index) => (
                  <li key={`${hint}-${index}`}>{hint}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-xl bg-white p-5 shadow-sm sm:p-6">
            <h2 className="text-lg font-semibold text-gray-900">
              Recommended Actions
            </h2>

            {incident.recommended_actions.length === 0 ? (
              <p className="mt-4 text-sm text-gray-500">
                No recommended actions available.
              </p>
            ) : (
              <ol className="mt-4 list-decimal space-y-2 pl-5 text-gray-600">
                {incident.recommended_actions.map((action, index) => (
                  <li key={`${action}-${index}`}>{action}</li>
                ))}
              </ol>
            )}
          </div>
        </section>

        <section className="rounded-xl bg-white p-5 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-gray-900">
              Incident Actions
            </h2>

            {isResolved && (
              <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700">
                Read-only: Resolved
              </span>
            )}
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void handleAcknowledge()}
              disabled={actionLoading || isAcknowledged || isResolved}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isAcknowledged ? "Acknowledged" : "Acknowledge"}
            </button>

            <button
              type="button"
              onClick={() => void handleUnassign()}
              disabled={actionLoading || !isAssigned || isResolved}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Unassign
            </button>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-2">
            <div className="min-w-0">
              <label
                htmlFor="assignedTo"
                className="text-sm font-medium text-gray-700"
              >
                Assign To
              </label>

              <div className="mt-2 flex min-w-0 flex-col gap-2 sm:flex-row">
                <input
                  id="assignedTo"
                  value={assignedTo}
                  onChange={(event) => setAssignedTo(event.target.value)}
                  placeholder="Username"
                  disabled={actionLoading || isResolved}
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none placeholder:text-gray-400 focus:border-blue-500 disabled:cursor-not-allowed disabled:bg-gray-100"
                />

                <button
                  type="button"
                  onClick={() => void handleAssign()}
                  disabled={actionLoading || isResolved}
                  className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Assign
                </button>
              </div>

              <p className="mt-2 text-xs text-gray-500">
                Current assignee: {incident.assigned_to || "Unassigned"}
              </p>
            </div>

            <div className="min-w-0">
              <label
                htmlFor="resolutionNotes"
                className="text-sm font-medium text-gray-700"
              >
                Resolution Notes
              </label>

              <textarea
                id="resolutionNotes"
                value={resolutionNotes}
                onChange={(event) =>
                  setResolutionNotes(event.target.value)
                }
                rows={3}
                disabled={actionLoading || isResolved}
                placeholder="Describe the resolution..."
                className="mt-2 w-full resize-y rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none placeholder:text-gray-400 focus:border-blue-500 disabled:cursor-not-allowed disabled:bg-gray-100"
              />

              <button
                type="button"
                onClick={() => void handleResolve()}
                disabled={actionLoading || isResolved}
                className="mt-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isResolved ? "Resolved" : "Resolve Incident"}
              </button>
            </div>
          </div>
        </section>

        <section className="rounded-xl bg-white p-5 shadow-sm sm:p-6">
          <h2 className="text-lg font-semibold text-gray-900">
            Incident Timeline
          </h2>

          {timeline.length === 0 ? (
            <p className="mt-4 text-sm text-gray-500">
              No timeline events available.
            </p>
          ) : (
            <div className="mt-6 space-y-5">
              {timeline.map((event) => (
                <div
                  key={event.id}
                  className="relative border-l-2 border-gray-200 pl-5"
                >
                  <div className="absolute -left-[7px] top-1 h-3 w-3 rounded-full bg-blue-600" />

                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="break-words font-semibold text-gray-900">
                      {event.event_type}
                    </span>

                    <span className="text-xs text-gray-500">
                      {formatDate(event.created_at)}
                    </span>
                  </div>

                  <p className="mt-1 break-words text-sm text-gray-600">
                    {event.message}
                  </p>

                  {event.status && (
                    <span
                      className={`mt-2 inline-block rounded-full px-2 py-1 text-xs ${badgeClass(event.status)}`}
                    >
                      {event.status}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <div>
          <Link
            href="/incidents"
            className="inline-block rounded-lg border border-gray-600 px-4 py-2 text-sm font-medium text-gray-200 transition hover:bg-gray-800"
          >
            Back to Incident List
          </Link>
        </div>
      </main>
    </AppShell>
  );
}
