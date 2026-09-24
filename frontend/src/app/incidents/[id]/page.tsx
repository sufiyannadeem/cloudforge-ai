"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import AppShell from "@/components/layout/AppShell";
import OperatorBriefing from "@/components/incidents/OperatorBriefing";
import IncidentTimeline from "@/components/incidents/IncidentTimeline";
import {
  acknowledgeIncident,
  analyzeIncidentDeterministic,
  assignIncident,
  getIncident,
  getIncidentTimeline,
  resolveIncident,
  unassignIncident,
} from "@/lib/incidents-api";

import type {
  AIAnalysis,
  Incident,
  IncidentTimelineEvent,
} from "@/types/incidents";

function formatDate(
  value: string | null | undefined,
): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function badgeClass(value: string): string {
  const normalized = value.toLowerCase();

  if (
    normalized === "critical" ||
    normalized === "p1" ||
    normalized === "p4"
  ) {
    return "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
  }

  if (
    normalized === "warning" ||
    normalized === "p2"
  ) {
    return "bg-yellow-100 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300";
  }

  if (
    normalized === "resolved" ||
    normalized === "succeeded"
  ) {
    return "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300";
  }

  if (
    normalized === "acknowledged" ||
    normalized === "assigned" ||
    normalized === "medium" ||
    normalized === "high"
  ) {
    return "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300";
  }

  return "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
}

function assessmentClass(
  assessment: string | null | undefined,
): string {
  switch (assessment) {
    case "alert_supported":
      return "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";

    case "alert_not_currently_observed":
      return "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300";

    case "evidence_available":
      return "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300";

    case "insufficient_evidence":
      return "bg-yellow-100 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300";

    default:
      return "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
  }
}

function formatAssessment(
  assessment: string | null | undefined,
): string {
  if (!assessment) {
    return "Not analyzed";
  }

  return assessment
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase(),
    );
}

function formatEvidenceValue(
  key: string,
  value: number | null,
): string {
  if (value === null || value === undefined) {
    return "Unavailable";
  }

  if (key === "error_rate") {
    return `${value.toFixed(2)}%`;
  }

  if (key === "p95_latency_seconds") {
    if (value < 1) {
      return `${(value * 1000).toFixed(2)} ms`;
    }

    return `${value.toFixed(2)} s`;
  }

  if (key === "request_rate") {
    return `${value.toFixed(4)} req/s`;
  }

  if (
    key === "service_up" ||
    key === "requests_in_flight" ||
    key === "deployments_in_progress" ||
    key === "deployment_failures" ||
    key === "deployment_total"
  ) {
    return Number.isInteger(value)
      ? String(value)
      : value.toFixed(2);
  }

  return value.toFixed(4);
}

function formatEvidenceLabel(
  key: string,
): string {
  const labels: Record<string, string> = {
    service_up: "Service Health",
    request_rate: "Request Rate",
    error_rate: "HTTP 5xx Error Rate",
    p95_latency_seconds: "P95 Latency",
    requests_in_flight: "Requests In Flight",
    deployments_in_progress: "Deployments In Progress",
    deployment_failures: "Deployment Failures",
    deployment_total: "Deployment Total",
  };

  return (
    labels[key] ??
    key
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) =>
        letter.toUpperCase(),
      )
  );
}

function formatTimeDifference(
  seconds: number,
): string {
  if (!Number.isFinite(seconds)) {
    return "Unknown";
  }

  const absoluteSeconds = Math.abs(seconds);

  if (absoluteSeconds < 60) {
    return `${absoluteSeconds.toFixed(1)} sec`;
  }

  if (absoluteSeconds < 3600) {
    return `${(absoluteSeconds / 60).toFixed(1)} min`;
  }

  return `${(absoluteSeconds / 3600).toFixed(1)} hr`;
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
        {title}
      </h2>

      <div className="mt-4">
        {children}
      </div>
    </section>
  );
}

function DeploymentCorrelationPanel({
  analysis,
}: {
  analysis: AIAnalysis;
}) {
  const correlations =
    analysis.deployment_correlations ?? [];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold text-gray-900 dark:text-white">
            Deployment Correlations
          </h3>

          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Historical deployments temporally correlated with this incident.
          </p>
        </div>

        <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-semibold text-gray-700 dark:bg-gray-800 dark:text-gray-300">
          {correlations.length}{" "}
          {correlations.length === 1
            ? "deployment"
            : "deployments"}
        </span>
      </div>

      {correlations.length === 0 ? (
        <div className="mt-4 rounded-lg border border-dashed border-gray-300 p-4 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
          No deployment was detected within the incident correlation window.
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          {correlations.map(
            (correlation, index) => (
              <div
                key={`${correlation.deployment_id}-${index}`}
                className="rounded-xl border border-gray-200 bg-gray-50 p-5 dark:border-gray-700 dark:bg-gray-800"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Deployment
                    </p>

                    <p className="mt-1 break-all font-mono text-sm font-semibold text-gray-900 dark:text-white">
                      {correlation.deployment_id}
                    </p>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-semibold ${badgeClass(
                        correlation.correlation_strength,
                      )}`}
                    >
                      Correlation:{" "}
                      {correlation.correlation_strength}
                    </span>

                    <span
                      className={`rounded-full px-3 py-1 text-xs font-semibold ${badgeClass(
                        correlation.status,
                      )}`}
                    >
                      {correlation.status}
                    </span>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Environment
                    </p>

                    <p className="mt-1 text-sm font-medium text-gray-900 dark:text-white">
                      {correlation.environment || "—"}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Incident Time Difference
                    </p>

                    <p className="mt-1 text-sm font-medium text-gray-900 dark:text-white">
                      {formatTimeDifference(
                        correlation.incident_time_difference_seconds,
                      )}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Correlation Type
                    </p>

                    <p className="mt-1 break-words text-sm font-medium text-gray-900 dark:text-white">
                      {correlation.correlation_type
                        .replaceAll("_", " ")}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Image
                    </p>

                    <p className="mt-1 break-all font-mono text-sm text-gray-900 dark:text-white">
                      {correlation.image || "—"}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Namespace
                    </p>

                    <p className="mt-1 font-mono text-sm text-gray-900 dark:text-white">
                      {correlation.namespace || "—"}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Git Commit
                    </p>

                    <p className="mt-1 break-all font-mono text-sm text-gray-900 dark:text-white">
                      {correlation.git_commit_sha || "—"}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Deployment Created
                    </p>

                    <p className="mt-1 text-sm text-gray-900 dark:text-white">
                      {formatDate(
                        correlation.deployment_created_at,
                      )}
                    </p>
                  </div>

                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      Deployment Updated
                    </p>

                    <p className="mt-1 text-sm text-gray-900 dark:text-white">
                      {formatDate(
                        correlation.deployment_updated_at,
                      )}
                    </p>
                  </div>
                </div>

                <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
                  <p className="text-xs font-semibold uppercase tracking-wide text-blue-700 dark:text-blue-300">
                    Correlation Analysis
                  </p>

                  <p className="mt-2 text-sm leading-6 text-blue-900 dark:text-blue-200">
                    {correlation.explanation}
                  </p>
                </div>
              </div>
            ),
          )}
        </div>
      )}
    </div>
  );
}

function AIAnalysisPanel({
  analysis,
  analyzing,
  onAnalyze,
}: {
  analysis: AIAnalysis | null;
  analyzing: boolean;
  onAnalyze: () => void;
}) {
  const evidenceEntries = useMemo(
    () =>
      Object.entries(
        analysis?.evidence ?? {},
      ),
    [analysis],
  );

  if (!analysis) {
    return (
      <Section title="Incident Intelligence">
        <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No incident intelligence has been generated yet.
          </p>

          <button
            type="button"
            onClick={onAnalyze}
            disabled={analyzing}
            className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {analyzing
              ? "Analyzing..."
              : "Analyze Incident"}
          </button>
        </div>
      </Section>
    );
  }

  return (
    <Section title="Incident Intelligence">
      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`rounded-full px-3 py-1 text-sm font-semibold ${assessmentClass(
              analysis.assessment,
            )}`}
          >
            {formatAssessment(
              analysis.assessment,
            )}
          </span>

          <span
            className={`rounded-full px-3 py-1 text-sm font-semibold ${badgeClass(
              analysis.confidence ?? "low",
            )}`}
          >
            Confidence:{" "}
            {analysis.confidence ?? "unknown"}
          </span>

          <span className="rounded-full bg-gray-100 px-3 py-1 text-sm font-semibold text-gray-700 dark:bg-gray-800 dark:text-gray-300">
            Provider: {analysis.provider}
          </span>

          {analysis.model && (
            <span className="rounded-full bg-gray-100 px-3 py-1 text-sm font-semibold text-gray-700 dark:bg-gray-800 dark:text-gray-300">
              Model: {analysis.model}
            </span>
          )}
        </div>

        {analysis.summary && (
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Analysis Summary
            </h3>

            <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-300">
              {analysis.summary}
            </p>
          </div>
        )}

        {analysis.probable_cause && (
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Evidence-Based Probable Cause
            </h3>

            <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-300">
              {analysis.probable_cause}
            </p>
          </div>
        )}

        <div>
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Operational Evidence
            </h3>

            <span className="text-xs text-gray-500 dark:text-gray-400">
              Generated{" "}
              {formatDate(
                analysis.generated_at,
              )}
            </span>
          </div>

          {evidenceEntries.length === 0 ? (
            <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
              No operational evidence was available.
            </p>
          ) : (
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {evidenceEntries.map(
                ([key, value]) => (
                  <div
                    key={key}
                    className="rounded-lg border border-gray-200 p-4 dark:border-gray-700"
                  >
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                      {formatEvidenceLabel(key)}
                    </p>

                    <p className="mt-2 text-xl font-bold text-gray-900 dark:text-white">
                      {formatEvidenceValue(
                        key,
                        value,
                      )}
                    </p>
                  </div>
                ),
              )}
            </div>
          )}
        </div>

        <div>
          <h3 className="font-semibold text-gray-900 dark:text-white">
            Evidence Findings
          </h3>

          {analysis.evidence_findings.length ===
          0 ? (
            <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
              No evidence findings were generated.
            </p>
          ) : (
            <ul className="mt-3 space-y-3">
              {analysis.evidence_findings.map(
                (finding, index) => (
                  <li
                    key={`${finding}-${index}`}
                    className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm leading-6 text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                  >
                    {finding}
                  </li>
                ),
              )}
            </ul>
          )}
        </div>

        <DeploymentCorrelationPanel
          analysis={analysis}
        />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Root Cause Hints
            </h3>

            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-gray-600 dark:text-gray-300">
              {analysis.root_cause_hints.length ===
              0 ? (
                <li>No hints available.</li>
              ) : (
                analysis.root_cause_hints.map(
                  (hint, index) => (
                    <li
                      key={`${hint}-${index}`}
                    >
                      {hint}
                    </li>
                  ),
                )
              )}
            </ul>
          </div>

          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Recommended Actions
            </h3>

            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-gray-600 dark:text-gray-300">
              {analysis.recommended_actions.length ===
              0 ? (
                <li>No actions available.</li>
              ) : (
                analysis.recommended_actions.map(
                  (action, index) => (
                    <li
                      key={`${action}-${index}`}
                    >
                      {action}
                    </li>
                  ),
                )
              )}
            </ol>
          </div>
        </div>

        {analysis.error && (
          <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800 dark:border-yellow-900 dark:bg-yellow-950 dark:text-yellow-300">
            Analysis provider warning:{" "}
            {analysis.error}
          </div>
        )}

        <div className="flex justify-end">
          <button
            type="button"
            onClick={onAnalyze}
            disabled={analyzing}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            {analyzing
              ? "Re-analyzing..."
              : "Re-analyze"}
          </button>
        </div>
      </div>
    </Section>
  );
}

export default function IncidentDetailsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const incidentId = params.id;

  const [incident, setIncident] =
    useState<Incident | null>(null);

  const [timeline, setTimeline] =
    useState<IncidentTimelineEvent[]>([]);

  const [assignedTo, setAssignedTo] =
    useState("");

  const [resolutionNotes, setResolutionNotes] =
    useState("");

  const [loading, setLoading] =
    useState(true);

  const [actionLoading, setActionLoading] =
    useState(false);

  const [analysisLoading, setAnalysisLoading] =
    useState(false);

  const [error, setError] =
    useState("");

  const loadIncident = useCallback(
    async () => {
      try {
        const result =
          await getIncident(incidentId);

        setIncident(result);

        setAssignedTo(
          result.assigned_to ?? "",
        );

        setResolutionNotes(
          result.resolution_notes ?? "",
        );
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load incident details.",
        );
      } finally {
        setLoading(false);
      }
    },
    [incidentId],
  );

  const loadTimeline = useCallback(
    async () => {
      try {
        const events =
          await getIncidentTimeline(
            incidentId,
          );

        setTimeline(events);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load incident timeline.",
        );
      }
    },
    [incidentId],
  );

  const refreshDetails = useCallback(
    async () => {
      setError("");

      await Promise.all([
        loadIncident(),
        loadTimeline(),
      ]);
    },
    [loadIncident, loadTimeline],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadInitialData() {
      try {
        setError("");

        const [
          incidentResult,
          timelineResult,
        ] = await Promise.all([
          getIncident(incidentId),
          getIncidentTimeline(incidentId),
        ]);

        if (cancelled) {
          return;
        }

        setIncident(incidentResult);

        setAssignedTo(
          incidentResult.assigned_to ?? "",
        );

        setResolutionNotes(
          incidentResult.resolution_notes ?? "",
        );

        setTimeline(timelineResult);
      } catch (err) {
        if (cancelled) {
          return;
        }

        setError(
          err instanceof Error
            ? err.message
            : "Unable to load incident details.",
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadInitialData();

    return () => {
      cancelled = true;
    };
  }, [incidentId]);

  async function handleAnalyze() {
    try {
      setAnalysisLoading(true);
      setError("");

      await analyzeIncidentDeterministic(
        incidentId,
      );

      await refreshDetails();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Incident analysis failed.",
      );
    } finally {
      setAnalysisLoading(false);
    }
  }

  async function handleAcknowledge() {
    try {
      setActionLoading(true);
      setError("");

      await acknowledgeIncident(
        incidentId,
        "nadeem",
      );

      await refreshDetails();
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
    if (!assignedTo.trim()) {
      setError(
        "Enter a user before assigning the incident.",
      );
      return;
    }

    try {
      setActionLoading(true);
      setError("");

      await assignIncident(
        incidentId,
        assignedTo.trim(),
      );

      await refreshDetails();
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
      setError("");

      await unassignIncident(
        incidentId,
      );

      await refreshDetails();
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
    if (!resolutionNotes.trim()) {
      setError(
        "Resolution notes are required.",
      );
      return;
    }

    try {
      setActionLoading(true);
      setError("");

      await resolveIncident(
        incidentId,
        resolutionNotes.trim(),
      );

      await refreshDetails();
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
        <div className="p-8 text-gray-500 dark:text-gray-400">
          Loading incident details...
        </div>
      </AppShell>
    );
  }

  if (!incident) {
    return (
      <AppShell>
        <div className="p-8">
          <p className="text-red-600">
            {error ||
              "Incident not found."}
          </p>

          <Link
            href="/incidents"
            className="mt-4 inline-block text-blue-600 hover:underline"
          >
            ← Back to incidents
          </Link>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <main className="space-y-6 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <Link
              href="/incidents"
              className="text-sm text-blue-600 hover:underline"
            >
              ← Back to incidents
            </Link>

            <p className="mt-4 text-sm text-blue-600 dark:text-blue-400">
              AIOps / Incident Intelligence
            </p>

            <h1 className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
              {incident.alert_name}
            </h1>

            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {incident.id}
            </p>
          </div>

          <button
            type="button"
            onClick={() => void refreshDetails()}
            disabled={
              actionLoading ||
              analysisLoading
            }
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            Refresh
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}

        <section className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Status
            </p>

            <span
              className={`mt-2 inline-block rounded-full px-3 py-1 text-sm font-semibold ${badgeClass(
                incident.status,
              )}`}
            >
              {incident.status}
            </span>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Severity
            </p>

            <span
              className={`mt-2 inline-block rounded-full px-3 py-1 text-sm font-semibold ${badgeClass(
                incident.severity,
              )}`}
            >
              {incident.severity}
            </span>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Priority
            </p>

            <span
              className={`mt-2 inline-block rounded-full px-3 py-1 text-sm font-semibold ${badgeClass(
                incident.priority,
              )}`}
            >
              {incident.priority}
            </span>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Alert Count
            </p>

            <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">
              {incident.alert_count}
            </p>
          </div>
        </section>

        <AIAnalysisPanel
          analysis={incident.ai_analysis}
          analyzing={analysisLoading}
          onAnalyze={() => void handleAnalyze()}
        />

	<OperatorBriefing
	  analysis={incident.ai_analysis}
	/>

        <Section title="Incident Overview">
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Service
              </p>

              <p className="mt-1 font-medium text-gray-900 dark:text-white">
                {incident.service}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Impact
              </p>

              <p className="mt-1 font-medium text-gray-900 dark:text-white">
                {incident.impact}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Confidence
              </p>

              <p className="mt-1 font-medium text-gray-900 dark:text-white">
                {incident.confidence}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Analysis Version
              </p>

              <p className="mt-1 font-medium text-gray-900 dark:text-white">
                {incident.analysis_version}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Created At
              </p>

              <p className="mt-1 font-medium text-gray-900 dark:text-white">
                {formatDate(
                  incident.created_at,
                )}
              </p>
            </div>

            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Updated At
              </p>

              <p className="mt-1 font-medium text-gray-900 dark:text-white">
                {formatDate(
                  incident.updated_at,
                )}
              </p>
            </div>
          </div>

          <div className="mt-6">
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Summary
            </h3>

            <p className="mt-2 text-gray-600 dark:text-gray-300">
              {incident.summary}
            </p>
          </div>

          <div className="mt-6">
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Original Probable Cause
            </h3>

            <p className="mt-2 text-gray-600 dark:text-gray-300">
              {incident.probable_cause ||
                "No probable cause available."}
            </p>
          </div>
        </Section>

        <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Section title="Root Cause Hints">
            {incident.root_cause_hints.length ===
            0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                No root-cause hints available.
              </p>
            ) : (
              <ul className="list-disc space-y-2 pl-5 text-sm text-gray-600 dark:text-gray-300">
                {incident.root_cause_hints.map(
                  (hint, index) => (
                    <li
                      key={`${hint}-${index}`}
                    >
                      {hint}
                    </li>
                  ),
                )}
              </ul>
            )}
          </Section>

          <Section title="Original Recommended Actions">
            {incident.recommended_actions.length ===
            0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                No recommended actions available.
              </p>
            ) : (
              <ol className="list-decimal space-y-2 pl-5 text-sm text-gray-600 dark:text-gray-300">
                {incident.recommended_actions.map(
                  (action, index) => (
                    <li
                      key={`${action}-${index}`}
                    >
                      {action}
                    </li>
                  ),
                )}
              </ol>
            )}
          </Section>
        </section>

        <Section title="Incident Actions">
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() =>
                void handleAcknowledge()
              }
              disabled={
                actionLoading ||
                Boolean(
                  incident.acknowledged_at,
                )
              }
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Acknowledge
            </button>

            <button
              type="button"
              onClick={() =>
                void handleUnassign()
              }
              disabled={
                actionLoading ||
                !incident.assigned_to
              }
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
            >
              Unassign
            </button>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label
                htmlFor="assignedTo"
                className="text-sm font-medium text-gray-700 dark:text-gray-200"
              >
                Assign To
              </label>

              <div className="mt-2 flex gap-2">
                <input
                  id="assignedTo"
                  value={assignedTo}
                  onChange={(event) =>
                    setAssignedTo(
                      event.target.value,
                    )
                  }
                  placeholder="Username"
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                />

                <button
                  type="button"
                  onClick={() =>
                    void handleAssign()
                  }
                  disabled={actionLoading}
                  className="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50 dark:bg-white dark:text-gray-900"
                >
                  Assign
                </button>
              </div>

              <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                Current assignee:{" "}
                {incident.assigned_to ||
                  "Unassigned"}
              </p>
            </div>

            <div>
              <label
                htmlFor="resolutionNotes"
                className="text-sm font-medium text-gray-700 dark:text-gray-200"
              >
                Resolution Notes
              </label>

              <textarea
                id="resolutionNotes"
                value={resolutionNotes}
                onChange={(event) =>
                  setResolutionNotes(
                    event.target.value,
                  )
                }
                rows={3}
                placeholder="Describe the resolution..."
                className="mt-2 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
              />

              <button
                type="button"
                onClick={() =>
                  void handleResolve()
                }
                disabled={
                  actionLoading ||
                  incident.status ===
                    "resolved"
                }
                className="mt-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Resolve Incident
              </button>
            </div>
          </div>
        </Section>

        <Section title="Incident Timeline">
          <IncidentTimeline
            events={timeline}
            formatDate={formatDate}
            badgeClass={badgeClass}
          />
        </Section>

        <div>
          <button
            type="button"
            onClick={() =>
              router.push("/incidents")
            }
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            Back to Incident List
          </button>
        </div>
      </main>
    </AppShell>
  );
}
