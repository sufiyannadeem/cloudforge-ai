"use client";

import { useCallback, useEffect, useState } from "react";

import AppShell from "@/components/layout/AppShell";
import {
  getSLOSummary,
  type SLOResult,
  type SLOStatus,
  type SLOSummary,
} from "@/lib/slo-api";

const EMPTY_SUMMARY: SLOSummary | null = null;

function formatPercent(
  value: number | null,
  decimals = 3,
): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `${(value * 100).toFixed(decimals)}%`;
}

function formatBurnRate(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `${value.toFixed(2)}x`;
}

function statusLabel(status: SLOStatus): string {
  switch (status) {
    case "healthy":
      return "Healthy";
    case "at_risk":
      return "At Risk";
    case "breached":
      return "Breached";
    case "insufficient_data":
      return "Insufficient Data";
  }
}

function statusClass(status: SLOStatus): string {
  switch (status) {
    case "healthy":
      return "border-emerald-700/50 bg-emerald-950/30 text-emerald-300";
    case "at_risk":
      return "border-amber-700/50 bg-amber-950/30 text-amber-300";
    case "breached":
      return "border-rose-700/50 bg-rose-950/30 text-rose-300";
    case "insufficient_data":
      return "border-gray-700 bg-gray-900/50 text-gray-400";
  }
}

function metricValue(slo: SLOResult): string {
  if (slo.compliance === null) {
    return "N/A";
  }

  if (slo.type === "latency") {
    return formatPercent(slo.compliance, 2);
  }

  return formatPercent(slo.compliance, 3);
}

function targetValue(slo: SLOResult): string {
  return formatPercent(slo.target, 3);
}

function SLOCard({
  slo,
}: {
  slo: SLOResult;
}) {
  const remaining =
    slo.error_budget_remaining === null
      ? "N/A"
      : formatPercent(
          slo.error_budget_remaining,
          1,
        );

  return (
    <article className="rounded-xl border border-[#29292f] bg-[#121214] p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-500">
            {slo.type.replace("_", " ")}
          </p>

          <h2 className="mt-1 text-xl font-semibold text-white">
            {slo.name}
          </h2>
        </div>

        <span
          className={`rounded-full border px-3 py-1 text-xs font-medium ${statusClass(
            slo.status,
          )}`}
        >
          {statusLabel(slo.status)}
        </span>
      </div>

      <p className="mt-3 text-sm leading-6 text-gray-500">
        {slo.description}
      </p>

      <div className="mt-6 grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-[#1a1a1f] p-4">
          <p className="text-xs uppercase tracking-wide text-gray-500">
            Observed
          </p>

          <p className="mt-2 text-xl font-semibold text-white">
            {metricValue(slo)}
          </p>
        </div>

        <div className="rounded-lg bg-[#1a1a1f] p-4">
          <p className="text-xs uppercase tracking-wide text-gray-500">
            Target
          </p>

          <p className="mt-2 text-xl font-semibold text-white">
            {targetValue(slo)}
          </p>
        </div>

        <div className="rounded-lg bg-[#1a1a1f] p-4">
          <p className="text-xs uppercase tracking-wide text-gray-500">
            Error budget
          </p>

          <p className="mt-2 text-xl font-semibold text-white">
            {remaining}
          </p>
        </div>

        <div className="rounded-lg bg-[#1a1a1f] p-4">
          <p className="text-xs uppercase tracking-wide text-gray-500">
            Burn rate
          </p>

          <p className="mt-2 text-xl font-semibold text-white">
            {formatBurnRate(slo.burn_rate)}
          </p>
        </div>
      </div>

      {slo.latency_threshold_ms !== null && (
        <div className="mt-4 text-xs text-gray-500">
          Latency threshold:{" "}
          <span className="text-gray-300">
            {slo.latency_threshold_ms} ms
          </span>
        </div>
      )}

      <div className="mt-4 border-t border-[#29292f] pt-4 text-xs text-gray-500">
        Observation window:{" "}
        <span className="text-gray-300">
          {slo.window}
        </span>
      </div>
    </article>
  );
}

function SummaryCard({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-[#29292f] bg-[#121214] p-5">
      <p className="text-xs uppercase tracking-wide text-gray-500">
        {label}
      </p>

      <p className="mt-2 text-3xl font-semibold text-white">
        {value}
      </p>

      <p className="mt-2 text-sm text-gray-500">
        {description}
      </p>
    </div>
  );
}

export default function SLOPage() {
  const [summary, setSummary] =
    useState<SLOSummary | null>(EMPTY_SUMMARY);

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
        const result = await getSLOSummary();

        setSummary(result);
      } catch (loadError) {
        setSummary(null);

        setError(
          loadError instanceof Error
            ? loadError.message
            : "Unable to load SLO data.",
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

  const overallStatus =
    summary?.overall_status ?? "insufficient_data";

  return (
    <AppShell>
      <main className="min-w-0 space-y-8 bg-[#09090b] p-4 text-gray-100 md:p-6">
        <section className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
          <div>
            <p className="text-sm font-medium text-indigo-400">
              Site Reliability Engineering
            </p>

            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">
              SLO & Error Budget
            </h1>

            <p className="mt-3 max-w-3xl text-sm leading-6 text-gray-400">
              Track service-level objectives, reliability
              compliance, error-budget consumption, and
              burn rate using Prometheus telemetry.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void loadSummary(true)}
            disabled={isRefreshing}
            className="rounded-lg border border-[#3b3b44] bg-[#151519] px-4 py-2 text-sm font-medium text-gray-200 transition hover:border-indigo-400 hover:bg-[#1c1c24] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRefreshing
              ? "Refreshing..."
              : "Refresh SLOs"}
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
                : statusLabel(overallStatus)
            }
            description="Aggregated state across configured SLOs."
          />

          <SummaryCard
            label="Healthy"
            value={summary?.healthy_count.toString() ?? "0"}
            description="SLOs currently meeting their target."
          />

          <SummaryCard
            label="At risk"
            value={summary?.at_risk_count.toString() ?? "0"}
            description="SLOs consuming budget quickly."
          />

          <SummaryCard
            label="Breached"
            value={summary?.breached_count.toString() ?? "0"}
            description="SLOs currently below target."
          />
        </section>

        <section className="rounded-xl border border-[#29292f] bg-[#121214] p-5">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div>
              <p className="text-sm text-gray-400">
                Monitoring target
              </p>

              <h2 className="mt-1 text-lg font-semibold text-white">
                {summary?.service ?? "Deployment Service"}
              </h2>
            </div>

            <div className="text-sm text-gray-500">
              Observation window:{" "}
              <span className="font-medium text-gray-300">
                {summary?.window ?? "7d"}
              </span>
            </div>
          </div>
        </section>

        <section>
          <div className="mb-4">
            <p className="text-sm font-medium text-indigo-400">
              Service-level objectives
            </p>

            <h2 className="mt-1 text-2xl font-semibold text-white">
              Reliability objectives
            </h2>

            <p className="mt-2 text-sm text-gray-500">
              Error budget represents the amount of
              unreliability permitted before the SLO target
              is exhausted.
            </p>
          </div>

          {summary?.slos.length ? (
            <div className="grid gap-4 lg:grid-cols-3">
              {summary.slos.map((slo) => (
                <SLOCard
                  key={`${slo.service}-${slo.type}`}
                  slo={slo}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-[#29292f] bg-[#121214] p-8 text-center text-sm text-gray-500">
              {isLoading
                ? "Loading SLO measurements..."
                : "No SLO measurements available."}
            </div>
          )}
        </section>

        <section className="rounded-xl border border-[#29292f] bg-[#121214] p-5">
          <p className="text-sm font-medium text-indigo-400">
            SRE interpretation
          </p>

          <h2 className="mt-1 text-xl font-semibold text-white">
            How to read the dashboard
          </h2>

          <div className="mt-5 space-y-4 text-sm leading-6 text-gray-400">
            <p>
              <span className="font-medium text-gray-200">
                SLO:
              </span>{" "}
              The reliability target the service is expected
              to maintain.
            </p>

            <p>
              <span className="font-medium text-gray-200">
                Error budget:
              </span>{" "}
              The allowed fraction of bad service before the
              SLO is exhausted.
            </p>

            <p>
              <span className="font-medium text-gray-200">
                Burn rate:
              </span>{" "}
              How quickly the observed bad-service rate is
              consuming the allowed error budget.
            </p>

            <p>
              <span className="font-medium text-gray-200">
                Insufficient data:
              </span>{" "}
              Prometheus does not have enough matching
              telemetry to make a reliable SLO calculation.
              It is not treated as a healthy result.
            </p>
          </div>
        </section>
      </main>
    </AppShell>
  );
}
