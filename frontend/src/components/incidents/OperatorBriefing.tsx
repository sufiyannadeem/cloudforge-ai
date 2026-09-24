"use client";

import type { AIAnalysis } from "@/types/incidents";

interface OperatorBriefingProps {
  analysis: AIAnalysis | null | undefined;
}

function formatAssessment(
  assessment: string | null | undefined,
): string {
  if (!assessment) {
    return "Unavailable";
  }

  return assessment
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) =>
      character.toUpperCase(),
    );
}

function formatProvider(
  provider: string | null | undefined,
): string {
  if (!provider) {
    return "Unknown";
  }

  if (provider === "deterministic") {
    return "Deterministic";
  }

  if (provider === "mock") {
    return "Mock AI";
  }

  if (provider === "openai_compatible") {
    return "AI Provider";
  }

  return provider;
}

function getSituation(
  analysis: AIAnalysis,
): string {
  const findings = analysis.evidence_findings ?? [];

  if (findings.length > 0) {
    return findings[0];
  }

  if (analysis.summary) {
    return analysis.summary;
  }

  return "No current operational assessment is available.";
}

function getActions(
  analysis: AIAnalysis,
): string[] {
  const actions = analysis.recommended_actions ?? [];

  return actions.slice(0, 4);
}

export default function OperatorBriefing({
  analysis,
}: OperatorBriefingProps) {
  if (!analysis) {
    return (
      <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="mb-2">
          <h2 className="text-lg font-semibold text-gray-900">
            Operator Briefing
          </h2>
        </div>

        <p className="text-sm text-gray-500">
          Incident intelligence has not been generated yet.
        </p>
      </section>
    );
  }

  const actions = getActions(analysis);

  return (
    <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Operator Briefing
          </h2>

          <p className="mt-1 text-sm text-gray-500">
            Evidence-aware summary for incident response.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700">
            {formatAssessment(analysis.assessment)}
          </span>

          <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
            Confidence:{" "}
            {analysis.confidence ?? "unknown"}
          </span>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Situation
          </p>

          <p className="mt-2 text-sm leading-6 text-gray-800">
            {getSituation(analysis)}
          </p>
        </div>

        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Analysis Source
          </p>

          <p className="mt-2 text-sm font-semibold text-gray-900">
            {formatProvider(analysis.provider)}
          </p>

          {analysis.model && (
            <p className="mt-1 break-all text-xs text-gray-500">
              {analysis.model}
            </p>
          )}
        </div>

        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Evidence State
          </p>

          <p className="mt-2 text-sm font-semibold text-gray-900">
            {analysis.status === "fallback"
              ? "AI rejected — deterministic fallback"
              : analysis.status === "ai_generated"
                ? "AI validated"
                : analysis.status === "deterministic"
                  ? "Deterministic analysis"
                  : analysis.status}
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">
            Assessment
          </h3>

          <p className="mt-2 text-sm leading-6 text-gray-600">
            {analysis.summary ||
              "No analysis summary is available."}
          </p>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-gray-900">
            Probable Cause
          </h3>

          <p className="mt-2 text-sm leading-6 text-gray-600">
            {analysis.probable_cause ||
              "No probable cause has been identified."}
          </p>
        </div>
      </div>

      {actions.length > 0 && (
        <div className="mt-5">
          <h3 className="text-sm font-semibold text-gray-900">
            Immediate Actions
          </h3>

          <ol className="mt-3 space-y-2">
            {actions.map((action, index) => (
              <li
                key={`${index}-${action}`}
                className="flex gap-3 rounded-xl border border-gray-100 bg-gray-50 p-3"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-900 text-xs font-semibold text-white">
                  {index + 1}
                </span>

                <span className="text-sm leading-6 text-gray-700">
                  {action}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {analysis.error && (
        <div className="mt-5 rounded-xl border border-yellow-200 bg-yellow-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-yellow-800">
            Provider Warning
          </p>

          <p className="mt-1 text-sm leading-6 text-yellow-900">
            {analysis.error}
          </p>
        </div>
      )}
    </section>
  );
}
