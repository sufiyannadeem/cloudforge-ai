"use client";

import { useCallback, useEffect, useState } from "react";

import AppShell from "@/components/layout/AppShell";
import {
  getSLOBurnRates,
  getSLOSummary,
  type SLOBurnRates,
  type SLOResult,
  type SLOStatus,
  type SLOSummary,
} from "@/lib/slo-api";

const EMPTY_SUMMARY: SLOSummary | null = null;

const EMPTY_BURN_RATES: SLOBurnRates = {
  availability: {
    "5m": null,
    "30m": null,
    "1h": null,
    "6h": null,
  },
  requestSuccess: {
    "5m": null,
    "30m": null,
    "1h": null,
    "6h": null,
  },
  latency: {
    "5m": null,
    "30m": null,
    "1h": null,
    "6h": null,
  },
  generatedAt: "",
};

function formatPercent(
  value: number | null,
  decimals = 2,
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
      return "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "at_risk":
      return "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "breached":
      return "border-rose-500/20 bg-rose-500/10 text-rose-700 dark:text-rose-300";
    case "insufficient_data":
      return "border-[var(--cf-border)] bg-[var(--cf-surface-3)] text-[var(--cf-text-secondary)]";
  }
}

function burnClass(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "text-[var(--cf-text-muted)]";
  }

  if (value >= 14.4) {
    return "text-rose-600 dark:text-rose-300";
  }

  if (value >= 6) {
    return "text-amber-600 dark:text-amber-300";
  }

  if (value >= 1) {
    return "text-orange-600 dark:text-orange-300";
  }

  return "text-emerald-600 dark:text-emerald-300";
}

function burnLabel(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "No data";
  }

  if (value >= 14.4) {
    return "Fast burn";
  }

  if (value >= 6) {
    return "Slow burn";
  }

  if (value >= 1) {
    return "Budget consuming";
  }

  return "Within budget";
}

function SLOCard({
  slo,
}: {
  slo: SLOResult;
}) {
  const remaining =
    slo.error_budget_remaining === null
      ? "N/A"
      : formatPercent(slo.error_budget_remaining, 1);

  return (
    <article className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--cf-text-muted)]">
            {slo.type.replace("_", " ")}
          </p>

          <h2 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
            {slo.name}
          </h2>
        </div>

        <span
          className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClass(
            slo.status,
          )}`}
        >
          {statusLabel(slo.status)}
        </span>
      </div>

      <p className="mt-3 text-sm leading-6 text-[var(--cf-text-secondary)]">
        {slo.description}
      </p>

      <div className="mt-5 grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3">
          <p className="text-xs text-[var(--cf-text-muted)]">
            Compliance
          </p>
          <p className="mt-1 text-lg font-semibold text-[var(--cf-text)]">
            {formatPercent(slo.compliance)}
          </p>
        </div>

        <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3">
          <p className="text-xs text-[var(--cf-text-muted)]">
            Target
          </p>
          <p className="mt-1 text-lg font-semibold text-[var(--cf-text)]">
            {formatPercent(slo.target)}
          </p>
        </div>

        <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3">
          <p className="text-xs text-[var(--cf-text-muted)]">
            Error budget remaining
          </p>
          <p className="mt-1 text-lg font-semibold text-[var(--cf-text)]">
            {remaining}
          </p>
        </div>

        <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3">
          <p className="text-xs text-[var(--cf-text-muted)]">
            Burn rate
          </p>
          <p
            className={`mt-1 text-lg font-semibold ${burnClass(
              slo.burn_rate,
            )}`}
          >
            {formatBurnRate(slo.burn_rate)}
          </p>
        </div>
      </div>
    </article>
  );
}

function BurnMetric({
  label,
  value,
}: {
  label: string;
  value: number | null;
}) {
  return (
    <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-[var(--cf-text-secondary)]">
          {label}
        </span>

        <span
          className={`text-lg font-semibold ${burnClass(value)}`}
        >
          {formatBurnRate(value)}
        </span>
      </div>

      <p
        className={`mt-1 text-xs font-medium ${burnClass(value)}`}
      >
        {burnLabel(value)}
      </p>
    </div>
  );
}

function BurnAnalysis({
  burnRates,
}: {
  burnRates: SLOBurnRates;
}) {
  const windows = ["5m", "30m", "1h", "6h"] as const;

  return (
    <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
      <div>
        <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
          SRE burn analysis
        </p>

        <h2 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
          Multi-window error-budget consumption
        </h2>

        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--cf-text-secondary)]">
          Burn rate shows how quickly each reliability objective is
          consuming its allowed error budget. Fast burn is
          14.4x or higher, slow burn is 6x or higher, and values
          above 1x indicate budget consumption.
        </p>
      </div>

      <div className="mt-6 overflow-x-auto">
        <div className="min-w-[760px]">
          <div className="grid grid-cols-[1.5fr_repeat(4,1fr)] gap-3 border-b border-[var(--cf-border)] pb-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-muted)]">
              SLO
            </div>

            {windows.map((window) => (
              <div
                key={window}
                className="text-center text-xs font-semibold uppercase tracking-wide text-[var(--cf-text-muted)]"
              >
                {window}
              </div>
            ))}
          </div>

          <div className="mt-3 space-y-3">
            <div className="grid grid-cols-[1.5fr_repeat(4,1fr)] gap-3">
              <div className="flex items-center text-sm font-medium text-[var(--cf-text)]">
                Availability
              </div>

              {windows.map((window) => (
                <BurnMetric
                  key={window}
                  label={window}
                  value={burnRates.availability[window]}
                />
              ))}
            </div>

            <div className="grid grid-cols-[1.5fr_repeat(4,1fr)] gap-3">
              <div className="flex items-center text-sm font-medium text-[var(--cf-text)]">
                Request success
              </div>

              {windows.map((window) => (
                <BurnMetric
                  key={window}
                  label={window}
                  value={burnRates.requestSuccess[window]}
                />
              ))}
            </div>

            <div className="grid grid-cols-[1.5fr_repeat(4,1fr)] gap-3">
              <div className="flex items-center text-sm font-medium text-[var(--cf-text)]">
                Latency
              </div>

              {windows.map((window) => (
                <BurnMetric
                  key={window}
                  label={window}
                  value={burnRates.latency[window]}
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-3 text-xs">
        <span className="rounded-full bg-emerald-500/10 px-3 py-1 font-medium text-emerald-700 dark:text-emerald-300">
          &lt; 1x — within budget
        </span>
        <span className="rounded-full bg-orange-500/10 px-3 py-1 font-medium text-orange-700 dark:text-orange-300">
          ≥ 1x — consuming budget
        </span>
        <span className="rounded-full bg-amber-500/10 px-3 py-1 font-medium text-amber-700 dark:text-amber-300">
          ≥ 6x — slow burn
        </span>
        <span className="rounded-full bg-rose-500/10 px-3 py-1 font-medium text-rose-700 dark:text-rose-300">
          ≥ 14.4x — fast burn
        </span>
      </div>
    </section>
  );
}

export default function SLOPage() {
  const [summary, setSummary] =
    useState<SLOSummary | null>(EMPTY_SUMMARY);
  const [burnRates, setBurnRates] =
    useState<SLOBurnRates>(EMPTY_BURN_RATES);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setError(null);

      const [nextSummary, nextBurnRates] =
        await Promise.all([
          getSLOSummary(),
          getSLOBurnRates(),
        ]);

      setSummary(nextSummary);
      setBurnRates(nextBurnRates);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load SLO data.",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void loadData();
    }, 30_000);

    return () => {
      window.clearInterval(interval);
    };
  }, [loadData]);

  const refreshOnMount = useCallback(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    const timeout = window.setTimeout(refreshOnMount, 0);

    return () => {
      window.clearTimeout(timeout);
    };
  }, [refreshOnMount]);

  return (
    <AppShell>
      <main className="min-w-0 space-y-6 bg-[var(--cf-background)] p-4 text-[var(--cf-text)] md:p-6">
        <header>
          <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
            Service-level objectives
          </p>

          <h1 className="mt-1 text-3xl font-bold tracking-tight text-[var(--cf-text)]">
            Reliability objectives
          </h1>

          <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--cf-text-secondary)]">
            Monitor service reliability, error budgets, and
            multi-window burn rates from one SRE control surface.
          </p>
        </header>

        {error && (
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-4">
            <p className="text-sm font-semibold text-rose-700 dark:text-rose-300">
              Unable to load SLO telemetry
            </p>

            <p className="mt-1 text-sm text-rose-700/80 dark:text-rose-300/80">
              {error}
            </p>
          </div>
        )}

        <section>
          <div className="mb-4">
            <h2 className="text-xl font-semibold text-[var(--cf-text)]">
              Current SLOs
            </h2>

            <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
              Seven-day reliability objectives for the selected
              service.
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
            <div className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-8 text-center text-sm text-[var(--cf-text-muted)]">
              {isLoading
                ? "Loading SLO measurements..."
                : "No SLO measurements available."}
            </div>
          )}
        </section>

        <BurnAnalysis burnRates={burnRates} />

        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
          <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
            SRE interpretation
          </p>

          <h2 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
            How to read the dashboard
          </h2>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {[
              [
                "SLO",
                "The reliability target the service is expected to maintain.",
              ],
              [
                "Error budget",
                "The allowed fraction of bad service before the SLO is exhausted.",
              ],
              [
                "Burn rate",
                "How quickly the observed bad-service rate is consuming the allowed error budget.",
              ],
              [
                "Insufficient data",
                "Prometheus does not have enough matching telemetry to make a reliable calculation.",
              ],
            ].map(([title, description]) => (
              <div
                key={title}
                className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4"
              >
                <p className="font-medium text-[var(--cf-text)]">
                  {title}
                </p>

                <p className="mt-1 text-sm leading-6 text-[var(--cf-text-secondary)]">
                  {description}
                </p>
              </div>
            ))}
          </div>
        </section>
      </main>
    </AppShell>
  );
}
