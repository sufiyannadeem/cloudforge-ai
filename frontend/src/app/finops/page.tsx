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
  estimateTerraformPlanCost,
} from "@/lib/finops-api";
import type {
  BudgetResponse,
  CostAnomalyResponse,
  CostAttributionResponse,
  CostHistoryResponse,
  CostTrendResponse,
  FinOpsReport,
  OptimizationReport,
  TerraformPlanCostEstimateResponse,
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

  const [terraformPlan, setTerraformPlan] = useState(`{
  "resource_changes": [
    {
      "address": "aws_instance.demo",
      "mode": "managed",
      "type": "aws_instance",
      "name": "demo",
      "change": {
        "actions": ["create"],
        "before": null,
        "after": {
          "region": "eu-west-1",
          "instance_type": "example"
        }
      }
    }
  ]
}`);

  const [terraformPricing, setTerraformPricing] = useState(`{
  "aws_instance.demo": {
    "unit_monthly_usd": 25,
    "source": "approved-pricing-evidence",
    "evidence_available": true,
    "confidence": "high",
    "assumptions": [
      "Monthly unit price supplied externally"
    ]
  }
}`);
  const [terraformResult, setTerraformResult] =
    useState<TerraformPlanCostEstimateResponse | null>(null);
  const [terraformLoading, setTerraformLoading] = useState(false);
  const [terraformError, setTerraformError] = useState<string | null>(null);

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

  const estimateTerraformCost = async () => {
    setTerraformError(null);
    setTerraformResult(null);

    if (!terraformPlan.trim()) {
      setTerraformError("Paste terraform show -json output first.");
      return;
    }

    let plan: unknown;
    let pricing: unknown = {};

    try {
      plan = JSON.parse(terraformPlan);
    } catch {
      setTerraformError("Terraform plan JSON is not valid JSON.");
      return;
    }

    if (
      typeof plan !== "object" ||
      plan === null ||
      Array.isArray(plan)
    ) {
      setTerraformError("Terraform plan must be a JSON object.");
      return;
    }

    if (terraformPricing.trim()) {
      try {
        pricing = JSON.parse(terraformPricing);
      } catch {
        setTerraformError("Pricing evidence JSON is not valid JSON.");
        return;
      }

      if (
        typeof pricing !== "object" ||
        pricing === null ||
        Array.isArray(pricing)
      ) {
        setTerraformError(
          "Pricing evidence must be a JSON object keyed by Terraform resource address.",
        );
        return;
      }
    }

    setTerraformLoading(true);

    try {
      const result = await estimateTerraformPlanCost(
        plan as Record<string, unknown>,
        pricing as Record<string, never>,
      );

      setTerraformResult(result);
    } catch (error) {
      setTerraformError(
        error instanceof Error
          ? error.message
          : "Terraform cost estimation failed.",
      );
    } finally {
      setTerraformLoading(false);
    }
  };

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

        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
          <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
            <div>
              <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">
                Infrastructure Cost Intelligence
              </p>

              <h2 className="mt-1 text-xl font-semibold">
                Terraform Cost Estimation
              </h2>

              <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--cf-text-secondary)]">
                Analyze an existing <code>terraform show -json</code> plan
                without executing Terraform or changing infrastructure.
                Pricing is only used when explicit evidence is supplied.
              </p>
            </div>

            <span className="rounded-full border border-[var(--cf-border)] px-3 py-1 text-xs font-medium text-[var(--cf-text-muted)]">
              Read-only
            </span>
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-2">
            <div>
              <label
                htmlFor="terraform-plan-json"
                className="text-sm font-medium"
              >
                Terraform plan JSON
              </label>

              <textarea
                id="terraform-plan-json"
                value={terraformPlan}
                onChange={(event) => setTerraformPlan(event.target.value)}
                placeholder="Paste output from: terraform show -json"
                className="mt-2 min-h-72 w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3 font-mono text-xs text-[var(--cf-text)] outline-none focus:border-indigo-500"
                spellCheck={false}
              />

              <p className="mt-2 text-xs leading-5 text-[var(--cf-text-muted)]">
                The service parses the supplied plan only. It does not run
                Terraform.
              </p>
            </div>

            <div>
              <label
                htmlFor="terraform-pricing-json"
                className="text-sm font-medium"
              >
                Pricing evidence JSON
              </label>

              <textarea
                id="terraform-pricing-json"
                value={terraformPricing}
                onChange={(event) => setTerraformPricing(event.target.value)}
                placeholder={`{
  "aws_instance.demo": {
    "unit_monthly_usd": 25,
    "source": "approved-pricing-evidence",
    "evidence_available": true,
    "confidence": "high",
    "assumptions": ["Monthly unit price supplied externally"]
  }
}`}
                className="mt-2 min-h-72 w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3 font-mono text-xs text-[var(--cf-text)] outline-none focus:border-indigo-500"
                spellCheck={false}
              />

              <p className="mt-2 text-xs leading-5 text-[var(--cf-text-muted)]">
                Leave empty when pricing evidence is unavailable. Unknown
                costs remain explicitly unknown rather than being treated as
                confirmed zero cost.
              </p>
            </div>
          </div>

          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
            <button
              type="button"
              onClick={() => void estimateTerraformCost()}
              disabled={terraformLoading}
              className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {terraformLoading
                ? "Estimating..."
                : "Estimate Terraform Cost"}
            </button>

            <p className="text-xs text-[var(--cf-text-muted)]">
              No AWS pricing lookup, Terraform execution, or infrastructure
              mutation is performed.
            </p>
          </div>

          {terraformError && (
            <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
              <p className="text-sm font-semibold text-amber-700 dark:text-amber-300">
                Terraform cost estimation failed
              </p>

              <p className="mt-1 text-xs leading-5 text-amber-700 dark:text-amber-200">
                {terraformError}
              </p>
            </div>
          )}

          {terraformResult && (
            <div className="mt-6 space-y-5">
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
                <Card
                  title="Parsed resources"
                  value={String(terraformResult.parsed_resource_count)}
                  description="Supported resources parsed from the plan."
                />

                <Card
                  title="Current monthly"
                  value={money(
                    terraformResult.cost_report.total_current_monthly_usd,
                  )}
                  description="Estimated current monthly cost."
                />

                <Card
                  title="Proposed monthly"
                  value={money(
                    terraformResult.cost_report.total_proposed_monthly_usd,
                  )}
                  description="Estimated proposed monthly cost."
                />

                <Card
                  title="Monthly delta"
                  value={money(
                    terraformResult.cost_report.total_monthly_delta_usd,
                  )}
                  description="Proposed minus current monthly cost."
                />

                <Card
                  title="Evidence coverage"
                  value={
                    terraformResult.cost_report.evidence_complete
                      ? "Complete"
                      : "Partial"
                  }
                  description="Whether every parsed resource has pricing evidence."
                />
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <article className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
                  <h3 className="font-semibold">
                    Unsupported resources
                  </h3>

                  {(terraformResult.unsupported_resources ?? []).length === 0 ? (
                    <p className="mt-2 text-sm text-[var(--cf-text-muted)]">
                      None reported.
                    </p>
                  ) : (
                    <ul className="mt-3 space-y-2">
                      {terraformResult.unsupported_resources.map((item) => (
                        <li
                          key={item}
                          className="rounded-md border border-[var(--cf-border)] p-2 font-mono text-xs"
                        >
                          {item}
                        </li>
                      ))}
                    </ul>
                  )}
                </article>

                <article className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
                  <h3 className="font-semibold">
                    Parser issues
                  </h3>

                  {(terraformResult.parse_issues ?? []).length === 0 ? (
                    <p className="mt-2 text-sm text-[var(--cf-text-muted)]">
                      No parser issues reported.
                    </p>
                  ) : (
                    <ul className="mt-3 space-y-2">
                      {terraformResult.parse_issues.map((issue) => (
                        <li
                          key={issue}
                          className="rounded-md border border-[var(--cf-border)] p-2 text-xs leading-5"
                        >
                          {issue}
                        </li>
                      ))}
                    </ul>
                  )}
                </article>
              </div>

              <div>
                <h3 className="font-semibold">
                  Resource estimates
                </h3>

                <div className="mt-3 overflow-x-auto rounded-lg border border-[var(--cf-border)]">
                  <table className="min-w-full text-left text-xs">
                    <thead className="bg-[var(--cf-surface-2)] text-[var(--cf-text-secondary)]">
                      <tr>
                        <th className="px-4 py-3 font-semibold">
                          Resource
                        </th>
                        <th className="px-4 py-3 font-semibold">
                          Action
                        </th>
                        <th className="px-4 py-3 font-semibold">
                          Region
                        </th>
                        <th className="px-4 py-3 font-semibold">
                          Current
                        </th>
                        <th className="px-4 py-3 font-semibold">
                          Proposed
                        </th>
                        <th className="px-4 py-3 font-semibold">
                          Delta
                        </th>
                        <th className="px-4 py-3 font-semibold">
                          Evidence
                        </th>
                      </tr>
                    </thead>

                    <tbody>
                      {(terraformResult.cost_report.estimates ?? []).map(
                        (estimate) => (
                          <tr
                            key={`${estimate.resource_id}-${estimate.action}`}
                            className="border-t border-[var(--cf-border)]"
                          >
                            <td className="px-4 py-3">
                              <div className="font-mono font-medium">
                                {estimate.resource_id}
                              </div>
                              <div className="mt-1 text-[var(--cf-text-muted)]">
                                {estimate.resource_type}
                              </div>
                            </td>

                            <td className="px-4 py-3">
                              {estimate.action}
                            </td>

                            <td className="px-4 py-3">
                              {estimate.region}
                            </td>

                            <td className="px-4 py-3">
                              {money(estimate.current_monthly_usd)}
                            </td>

                            <td className="px-4 py-3">
                              {money(estimate.proposed_monthly_usd)}
                            </td>

                            <td className="px-4 py-3 font-semibold">
                              {money(estimate.monthly_delta_usd)}
                            </td>

                            <td className="px-4 py-3">
                              {estimate.evidence_available
                                ? "Available"
                                : "Missing"}
                            </td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
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
