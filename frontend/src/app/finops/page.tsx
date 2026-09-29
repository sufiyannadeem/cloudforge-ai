"use client";

import { useCallback, useEffect, useState } from "react";

import AppShell from "@/components/layout/AppShell";
import {
  getBudgets,
  getCostAnomalies,
  getCostAttribution,
  getCostHistory,
  getCostTrend,
  getFinOpsReport,
  getKubernetesOptimization,
} from "@/lib/finops-api";
import type {
  BudgetResponse,
  CostAnomalyResponse,
  CostAttributionResponse,
  CostHistoryResponse,
  CostTrendResponse,
  FinOpsReport,
  OptimizationReport,
} from "@/types/finops";

const EMPTY_HISTORY: CostHistoryResponse = {
  start_date: "",
  end_date: "",
  total_cost: 0,
  average_daily_cost: 0,
  points: [],
};

const EMPTY_TREND: CostTrendResponse = {
  start_date: "",
  end_date: "",
  comparison_start_date: "",
  comparison_end_date: "",
  current_cost: 0,
  previous_cost: 0,
  change_amount: 0,
  change_percent: null,
  trend: "stable",
  currency: "USD",
};

const EMPTY_ANOMALIES: CostAnomalyResponse = {
  start_date: "",
  end_date: "",
  threshold: 2.5,
  anomalies: [],
};

const EMPTY_ATTRIBUTION: CostAttributionResponse = {
  start_date: "",
  end_date: "",
  dimension: "service",
  total_cost: 0,
  entries: [],
};

const EMPTY_BUDGETS: BudgetResponse = {
  account_id: "",
  budgets: [],
};

const EMPTY_OPTIMIZATION: OptimizationReport = {
  generated_by: "cloudforge-finops-v2b",
  findings: [],
  total_potential_monthly_savings_usd: 0,
  finding_count: 0,
};

function money(value: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

function percent(value: number | null): string {
  return value === null ? "N/A" : `${value.toFixed(1)}%`;
}

function Card({
  title,
  value,
  description,
}: {
  title: string;
  value: string;
  description: string;
}) {
  return (
    <article className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
      <p className="text-sm font-medium text-[var(--cf-text-secondary)]">
        {title}
      </p>
      <p className="mt-2 text-3xl font-bold tracking-tight text-[var(--cf-text)]">
        {value}
      </p>
      <p className="mt-2 text-xs leading-5 text-[var(--cf-text-muted)]">
        {description}
      </p>
    </article>
  );
}

export default function FinOpsPage() {
  const [report, setReport] = useState<FinOpsReport | null>(null);
  const [history, setHistory] =
    useState<CostHistoryResponse>(EMPTY_HISTORY);
  const [trend, setTrend] =
    useState<CostTrendResponse>(EMPTY_TREND);
  const [anomalies, setAnomalies] =
    useState<CostAnomalyResponse>(EMPTY_ANOMALIES);
  const [attribution, setAttribution] =
    useState<CostAttributionResponse>(EMPTY_ATTRIBUTION);
  const [budgets, setBudgets] =
    useState<BudgetResponse>(EMPTY_BUDGETS);
  const [optimization, setOptimization] =
    useState<OptimizationReport>(EMPTY_OPTIMIZATION);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    const results = await Promise.allSettled([
      getFinOpsReport(),
      getCostHistory(),
      getCostTrend(),
      getCostAnomalies(),
      getCostAttribution(),
      getBudgets(),
      getKubernetesOptimization(),
    ]);

    const errors: string[] = [];

    const [
      reportResult,
      historyResult,
      trendResult,
      anomalyResult,
      attributionResult,
      budgetsResult,
      optimizationResult,
    ] = results;

    if (reportResult.status === "fulfilled") {
      setReport(reportResult.value);
    } else {
      errors.push("AWS FinOps report unavailable");
    }

    if (historyResult.status === "fulfilled") {
      setHistory(historyResult.value);
    } else {
      errors.push("Cost history unavailable");
    }

    if (trendResult.status === "fulfilled") {
      setTrend(trendResult.value);
    } else {
      errors.push("Cost trend unavailable");
    }

    if (anomalyResult.status === "fulfilled") {
      setAnomalies(anomalyResult.value);
    } else {
      errors.push("Cost anomaly analysis unavailable");
    }

    if (attributionResult.status === "fulfilled") {
      setAttribution(attributionResult.value);
    } else {
      errors.push("Cost attribution unavailable");
    }

    if (budgetsResult.status === "fulfilled") {
      setBudgets(budgetsResult.value);
    } else {
      errors.push("AWS budgets unavailable");
    }

    if (optimizationResult.status === "fulfilled") {
      setOptimization(optimizationResult.value);
    } else {
      errors.push("Kubernetes optimization unavailable");
    }

    setError(errors.length ? errors.join(" · ") : null);
    setLastUpdated(new Date().toLocaleTimeString());
    setLoading(false);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <AppShell>
      <main className="min-w-0 space-y-6 bg-[var(--cf-background)] p-4 text-[var(--cf-text)] md:p-6">
        <header className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
              Platform Engineering
            </p>

            <h1 className="mt-1 text-3xl font-bold tracking-tight">
              FinOps
            </h1>

            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--cf-text-secondary)]">
              Cloud cost intelligence, workload optimization,
              budget visibility and evidence-based savings
              recommendations.
            </p>
          </div>

          <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-3 py-2 text-xs text-[var(--cf-text-muted)]">
            {loading
              ? "Refreshing..."
              : `Updated ${lastUpdated ?? "just now"}`}
          </div>
        </header>

        {error && (
          <section className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
            <p className="text-sm font-semibold text-amber-700 dark:text-amber-300">
              Some FinOps data could not be loaded
            </p>
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-200">
              {error}
            </p>
          </section>
        )}

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Card
            title="Current period cost"
            value={money(history.total_cost)}
            description="AWS Cost Explorer total for the selected period."
          />

          <Card
            title="Daily average"
            value={money(history.average_daily_cost)}
            description="Average AWS cost per day."
          />

          <Card
            title="Period change"
            value={percent(trend.change_percent)}
            description="Change compared with the previous period."
          />

          <Card
            title="Potential monthly savings"
            value={money(
              optimization.total_potential_monthly_savings_usd
            )}
            description="Deterministic Kubernetes optimization estimate."
          />
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <article className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
            <h2 className="text-xl font-semibold">Cost trend</h2>
            <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
              Current and previous period comparison.
            </p>

            <div className="mt-5 grid grid-cols-2 gap-4">
              <Card
                title="Current"
                value={money(trend.current_cost)}
                description="Selected period."
              />
              <Card
                title="Previous"
                value={money(trend.previous_cost)}
                description="Previous equivalent period."
              />
            </div>
          </article>

          <article className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
            <h2 className="text-xl font-semibold">Cost anomalies</h2>
            <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
              Statistical cost deviations detected in the selected window.
            </p>

            <p className="mt-5 text-3xl font-bold">
              {(anomalies.anomalies ?? []).length}
            </p>

            <p className="mt-1 text-xs text-[var(--cf-text-muted)]">
              Detected anomalies
            </p>
          </article>
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <article className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
            <h2 className="text-xl font-semibold">
              AWS resource inventory
            </h2>

            <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
              Read-only AWS resource evidence collected by FinOps.
            </p>

            <div className="mt-5 grid grid-cols-2 gap-4">
              <Card
                title="Resources"
                value={String(report?.resources?.length ?? 0)}
                description="Resources returned by the AWS collector."
              />

              <Card
                title="Region"
                value={report?.region ?? "N/A"}
                description="AWS region represented by the report."
              />
            </div>
          </article>

          <article className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
            <h2 className="text-xl font-semibold">
              Budget status
            </h2>

            <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
              AWS budget utilization and forecast visibility.
            </p>

            <div className="mt-4 space-y-3">
              {(budgets.budgets ?? []).length === 0 ? (
                <p className="text-sm text-[var(--cf-text-muted)]">
                  No budgets returned.
                </p>
              ) : (
                (budgets.budgets ?? []).map((budget) => (
                  <div
                    key={budget.name}
                    className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <p className="font-medium">{budget.name}</p>
                      <span className="text-xs uppercase">
                        {budget.status}
                      </span>
                    </div>

                    <p className="mt-2 text-sm text-[var(--cf-text-secondary)]">
                      Actual:{" "}
                      {percent(
                        budget.actual_utilization_percent,
                      )}
                      {" · "}
                      Forecast:{" "}
                      {percent(
                        budget.forecast_utilization_percent,
                      )}
                    </p>
                  </div>
                ))
              )}
            </div>
          </article>
        </section>

        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
          <h2 className="text-xl font-semibold">
            Cost attribution
          </h2>

          <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
            AWS cost grouped by service.
          </p>

          <div className="mt-5 space-y-3">
            {(attribution.entries ?? []).length === 0 ? (
              <p className="text-sm text-[var(--cf-text-muted)]">
                No attribution data returned.
              </p>
            ) : (
              (attribution.entries ?? []).slice(0, 10).map((entry) => (
                <div
                  key={`${entry.dimension}-${entry.value}`}
                  className="flex items-center justify-between rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4"
                >
                  <span className="font-medium">
                    {entry.value}
                  </span>
                  <span className="font-semibold">
                    {money(entry.amount, entry.currency)}
                  </span>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
          <div>
            <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
              Optimization
            </p>

            <h2 className="mt-1 text-xl font-semibold">
              Evidence-based recommendations
            </h2>

            <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
              Recommendations are read-only and require human approval
              before any operational action.
            </p>
          </div>

          <div className="mt-5 space-y-3">
            {((optimization.findings ?? []).length) === 0 ? (
              <p className="text-sm text-[var(--cf-text-muted)]">
                No optimization recommendations returned.
              </p>
            ) : (
              (optimization.findings ?? [])
      .slice(0, 10)
      .map((recommendation, index) => (
                  <div
                    key={`${recommendation.resource_id ?? "resource"}-${index}`}
                    className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4"
                  >
                    <div className="flex flex-col justify-between gap-2 md:flex-row">
                      <div>
        <p className="font-medium">
            {recommendation.domain} · {recommendation.severity}
        </p>
        <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
            {recommendation.recommendation}
        </p>
      </div>

                      <div className="shrink-0 text-sm font-semibold">
                        {money(
                          recommendation.potential_monthly_savings_usd
                        )}
                        /mo
                      </div>
                    </div>

                    <p className="mt-3 text-xs font-medium uppercase text-amber-600 dark:text-amber-300">
                      {recommendation.action}
                    </p>
                  </div>
                ))
            )}
          </div>
        </section>

        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-4 py-2 text-sm font-medium shadow-sm transition hover:bg-[var(--cf-surface-2)] disabled:opacity-50"
          >
            {loading ? "Refreshing..." : "Refresh FinOps"}
          </button>
        </div>
      </main>
    </AppShell>
  );
}
