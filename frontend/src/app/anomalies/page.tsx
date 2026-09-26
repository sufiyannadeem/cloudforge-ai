"use client";

import { useCallback, useEffect, useState } from "react";

import AppShell from "@/components/layout/AppShell";
import { getAnomalySummary } from "@/lib/anomaly-api";
import type {
  AnomalyClassification,
  AnomalyDirection,
  AnomalyMetric,
  AnomalySummary,
} from "@/types/anomaly";

function classificationLabel(
  classification: AnomalyClassification,
): string {
  switch (classification) {
    case "normal":
      return "Normal";
    case "anomaly":
      return "Anomaly";
    case "critical":
      return "Critical";
    case "insufficient_data":
      return "Insufficient Data";
  }
}

function classificationClass(
  classification: AnomalyClassification,
): string {
  switch (classification) {
    case "normal":
      return "border-emerald-700/50 bg-emerald-950/30 text-emerald-300";

    case "anomaly":
      return "border-amber-700/50 bg-amber-950/30 text-amber-300";

    case "critical":
      return "border-rose-700/50 bg-rose-950/30 text-rose-300";

    case "insufficient_data":
      return "border-[var(--cf-border)] bg-[var(--cf-surface-2)] text-[var(--cf-text-muted)]";
  }
}

function directionLabel(
  direction: AnomalyDirection,
): string {
  switch (direction) {
    case "increase":
      return "Increasing";
    case "decrease":
      return "Decreasing";
    case "stable":
      return "Stable";
  }
}

function directionClass(
  direction: AnomalyDirection,
): string {
  switch (direction) {
    case "increase":
      return "text-amber-300";
    case "decrease":
      return "text-blue-300";
    case "stable":
      return "text-[var(--cf-text-secondary)]";
  }
}

function formatMetricValue(
  metric: AnomalyMetric,
): string {
  const value = metric.current_value;

  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  switch (metric.unit) {
    case "percent":
      return `${value.toFixed(2)}%`;

    case "requests_per_second":
      return `${value.toFixed(3)} req/s`;

    case "seconds":
      if (value < 1) {
        return `${(value * 1000).toFixed(2)} ms`;
      }

      return `${value.toFixed(2)} s`;

    default:
      return value.toFixed(2);
  }
}

function formatBaselineValue(
  metric: AnomalyMetric,
): string {
  const value = metric.baseline_value;

  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  switch (metric.unit) {
    case "percent":
      return `${value.toFixed(2)}%`;

    case "requests_per_second":
      return `${value.toFixed(3)} req/s`;

    case "seconds":
      if (value < 1) {
        return `${(value * 1000).toFixed(2)} ms`;
      }

      return `${value.toFixed(2)} s`;

    default:
      return value.toFixed(2);
  }
}

function formatDeviation(
  value: number | null,
): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `${value.toFixed(1)}%`;
}

function formatZScore(
  value: number | null,
): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return value.toFixed(2);
}

function formatDate(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function SummaryCard({
  label,
  value,
  description,
}: {
  label: string;
  value: string | number;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5">
      <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
        {label}
      </p>

      <p className="mt-2 text-3xl font-semibold text-[var(--cf-text)]">
        {value}
      </p>

      <p className="mt-2 text-sm text-[var(--cf-text-muted)]">
        {description}
      </p>
    </div>
  );
}

function MetricCard({
  metric,
}: {
  metric: AnomalyMetric;
}) {
  return (
    <article className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
            Telemetry signal
          </p>

          <h2 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
            {metric.display_name}
          </h2>
        </div>

        <span
          className={`w-fit rounded-full border px-3 py-1 text-xs font-medium ${classificationClass(
            metric.classification,
          )}`}
        >
          {classificationLabel(metric.classification)}
        </span>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
          <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
            Current
          </p>

          <p className="mt-2 text-xl font-semibold text-[var(--cf-text)]">
            {formatMetricValue(metric)}
          </p>
        </div>

        <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
          <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
            Baseline
          </p>

          <p className="mt-2 text-xl font-semibold text-[var(--cf-text)]">
            {formatBaselineValue(metric)}
          </p>
        </div>

        <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
          <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
            Deviation
          </p>

          <p className="mt-2 text-xl font-semibold text-[var(--cf-text)]">
            {formatDeviation(metric.deviation_percent)}
          </p>
        </div>

        <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
          <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
            Z-score
          </p>

          <p className="mt-2 text-xl font-semibold text-[var(--cf-text)]">
            {formatZScore(metric.z_score)}
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 border-t border-[var(--cf-border)] pt-4 sm:grid-cols-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
            Direction
          </p>

          <p
            className={`mt-1 text-sm font-medium ${directionClass(
              metric.direction,
            )}`}
          >
            {directionLabel(metric.direction)}
          </p>
        </div>

        <div>
          <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
            Samples
          </p>

          <p className="mt-1 text-sm font-medium text-[var(--cf-text-secondary)]">
            {metric.sample_count}
          </p>
        </div>

        <div>
          <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
            Evaluated
          </p>

          <p className="mt-1 text-sm font-medium text-[var(--cf-text-secondary)]">
            {formatDate(metric.evaluated_at)}
          </p>
        </div>
      </div>

      <div className="mt-5 rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-muted)]">
          Evidence
        </p>

        <ul className="mt-3 space-y-2">
          {metric.evidence.map((item, index) => (
            <li
              key={`${metric.name}-evidence-${index}`}
              className="flex gap-2 text-sm leading-6 text-[var(--cf-text-secondary)]"
            >
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
}

export default function AnomaliesPage() {
  const [summary, setSummary] =
    useState<AnomalySummary | null>(null);

  const [isLoading, setIsLoading] =
    useState(true);

  const [isRefreshing, setIsRefreshing] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const loadSummary = useCallback(
    async (manualRefresh = false) => {
      if (manualRefresh) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }

      setError(null);

      try {
        const result = await getAnomalySummary();

        setSummary(result);
      } catch (loadError) {
        setSummary(null);

        setError(
          loadError instanceof Error
            ? loadError.message
            : "Unable to load anomaly data.",
        );
      } finally {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void loadSummary();
    }, 0);

    const interval = window.setInterval(() => {
      void loadSummary(true);
    }, 30000);

    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
    };
  }, [loadSummary]);

  const overallClassification =
    summary?.overall_classification ??
    "insufficient_data";

  return (
    <AppShell>
      <main className="min-w-0 space-y-8 bg-[var(--cf-background)] p-4 text-[var(--cf-text)] md:p-6">
        <section className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
          <div>
            <p className="text-sm font-medium text-indigo-400">
              AIOps / Anomaly Detection
            </p>

            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[var(--cf-text)]">
              Anomaly Detection
            </h1>

            <p className="mt-3 max-w-3xl text-sm leading-6 text-[var(--cf-text-secondary)]">
              Detect statistically unusual changes in service
              telemetry using historical baselines, deviation,
              and z-score analysis.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void loadSummary(true)}
            disabled={isRefreshing}
            className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-4 py-2 text-sm font-medium text-[var(--cf-text)] transition hover:border-indigo-400 hover:bg-[var(--cf-surface-2)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRefreshing
              ? "Refreshing..."
              : "Refresh Detection"}
          </button>
        </section>

        {error && (
          <div className="rounded-xl border border-rose-700/60 bg-rose-950/30 p-4 text-sm text-rose-300">
            {error}
          </div>
        )}

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryCard
            label="Overall status"
            value={
              isLoading
                ? "Loading..."
                : classificationLabel(
                    overallClassification,
                  )
            }
            description="Aggregated classification across telemetry signals."
          />

          <SummaryCard
            label="Normal"
            value={summary?.normal_count ?? 0}
            description="Signals within expected historical behavior."
          />

          <SummaryCard
            label="Anomalies"
            value={summary?.anomaly_count ?? 0}
            description="Signals showing statistically unusual behavior."
          />

          <SummaryCard
            label="Critical"
            value={summary?.critical_count ?? 0}
            description="Signals showing severe deviation from baseline."
          />
        </section>

        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <p className="text-sm text-[var(--cf-text-secondary)]">
                Detection target
              </p>

              <h2 className="mt-1 text-lg font-semibold text-[var(--cf-text)]">
                {summary?.service ?? "Deployment Service"}
              </h2>
            </div>

            <div className="grid grid-cols-2 gap-5 text-sm">
              <div>
                <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
                  Window
                </p>

                <p className="mt-1 font-medium text-[var(--cf-text-secondary)]">
                  {summary?.window_minutes ?? 60} minutes
                </p>
              </div>

              <div>
                <p className="text-xs uppercase tracking-wide text-[var(--cf-text-muted)]">
                  Resolution
                </p>

                <p className="mt-1 font-medium text-[var(--cf-text-secondary)]">
                  {summary?.step_seconds ?? 60}s
                </p>
              </div>
            </div>
          </div>
        </section>

        <section>
          <div className="mb-4">
            <p className="text-sm font-medium text-indigo-400">
              Telemetry signals
            </p>

            <h2 className="mt-1 text-2xl font-semibold text-[var(--cf-text)]">
              Service behavior analysis
            </h2>

            <p className="mt-2 text-sm text-[var(--cf-text-muted)]">
              Each signal compares the latest observation against
              its historical baseline.
            </p>
          </div>

          {summary?.metrics.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {summary.metrics.map((metric) => (
                <MetricCard
                  key={metric.name}
                  metric={metric}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-8 text-center text-sm text-[var(--cf-text-muted)]">
              {isLoading
                ? "Loading anomaly measurements..."
                : "No anomaly measurements available."}
            </div>
          )}
        </section>

        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5">
          <p className="text-sm font-medium text-indigo-400">
            AIOps interpretation
          </p>

          <h2 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
            How anomaly detection works
          </h2>

          <div className="mt-5 space-y-4 text-sm leading-6 text-[var(--cf-text-secondary)]">
            <p>
              <span className="font-medium text-[var(--cf-text)]">
                Baseline:
              </span>{" "}
              Historical telemetry is used to establish the
              expected behavior of each monitored signal.
            </p>

            <p>
              <span className="font-medium text-[var(--cf-text)]">
                Deviation:
              </span>{" "}
              The current observation is compared with the
              historical baseline to determine how far behavior
              has changed.
            </p>

            <p>
              <span className="font-medium text-[var(--cf-text)]">
                Z-score:
              </span>{" "}
              Statistical distance from the historical mean helps
              identify behavior that is unusual relative to normal
              variation.
            </p>

            <p>
              <span className="font-medium text-[var(--cf-text)]">
                Evidence:
              </span>{" "}
              Every classification includes the observed value,
              baseline, deviation, and statistical context so an
              operator can understand why the signal was classified
              that way.
            </p>

            <p>
              <span className="font-medium text-[var(--cf-text)]">
                Insufficient data:
              </span>{" "}
              Missing or insufficient telemetry is not interpreted
              as healthy behavior.
            </p>
          </div>
        </section>

        {summary && (
          <div className="border-t border-[var(--cf-border)] pt-4 text-xs text-[var(--cf-text-muted)]">
            Last detection run:{" "}
            <span className="text-[var(--cf-text-secondary)]">
              {formatDate(summary.generated_at)}
            </span>
          </div>
        )}
      </main>
    </AppShell>
  );
}
