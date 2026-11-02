"use client";

import { useCallback, useEffect, useState } from "react";

import Link from "next/link";

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
import {
  buildRightsizingHref,
  getRightsizingRequest,
} from "@/lib/rightsizing";
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

const DEMO_ANOMALIES: CostAnomalyResponse = {
  start_date: "2026-09-10",
  end_date: "2026-10-10",
  threshold: 2.5,
  anomalies: [
    {
      date: "2026-09-22",
      amount: 28.4,
      expected_amount: 11.2,
      deviation: 17.2,
      score: 4.1,
    },
    {
      date: "2026-10-03",
      amount: 24.7,
      expected_amount: 12.1,
      deviation: 12.6,
      score: 3.2,
    },
    {
      date: "2026-10-08",
      amount: 19.9,
      expected_amount: 11.5,
      deviation: 8.4,
      score: 2.7,
    },
  ],
};

const DEMO_HISTORY: CostHistoryResponse = {
  start_date: "2026-09-10",
  end_date: "2026-10-10",
  total_cost: 348.6,
  average_daily_cost: 11.62,
  points: [
    { date: "2026-09-10", amount: 11.2, currency: "USD" },
    { date: "2026-09-20", amount: 11.6, currency: "USD" },
    { date: "2026-10-01", amount: 12.1, currency: "USD" },
    { date: "2026-10-10", amount: 11.5, currency: "USD" },
  ],
};

const DEMO_TREND: CostTrendResponse = {
  start_date: "2026-09-10",
  end_date: "2026-10-10",
  comparison_start_date: "2026-08-10",
  comparison_end_date: "2026-09-10",
  current_cost: 348.6,
  previous_cost: 363.88,
  change_amount: -15.28,
  change_percent: -4.2,
  trend: "improving",
  currency: "USD",
};

const DEMO_ATTRIBUTION: CostAttributionResponse = {
  start_date: "2026-09-10",
  end_date: "2026-10-10",
  dimension: "service",
  total_cost: 348.6,
  entries: [
    { dimension: "service", value: "Amazon EC2 (Compute)", amount: 150.0, currency: "USD" },
    { dimension: "service", value: "Amazon EKS (Kubernetes)", amount: 73.0, currency: "USD" },
    { dimension: "service", value: "Amazon RDS (PostgreSQL)", amount: 55.5, currency: "USD" },
    { dimension: "service", value: "Elastic Load Balancing (ALB)", amount: 45.0, currency: "USD" },
    { dimension: "service", value: "Amazon S3 (Storage)", amount: 18.1, currency: "USD" },
    { dimension: "service", value: "Amazon VPC & Networking", amount: 7.0, currency: "USD" },
  ],
};

const DEMO_BUDGETS: BudgetResponse = {
  account_id: "123456789012",
  budgets: [
    {
      name: "CloudForge-Monthly-Platform-Budget",
      budget_type: "COST",
      time_unit: "MONTHLY",
      limit: 400.0,
      actual_spend: 348.6,
      forecasted_spend: 376.8,
      actual_utilization_percent: 87.15,
      forecast_utilization_percent: 94.2,
      currency: "USD",
      status: "OK",
      cost_filters: {},
    },
  ],
};

const DEMO_OPTIMIZATION: OptimizationReport = {
  generated_by: "cloudforge-finops-v2b",
  findings: [
    {
      domain: "ec2",
      resource_id: "i-0abcdef1234567890 (t3.large)",
      severity: "warning",
      metric: "cpu_utilization",
      observed_value: 8.0,
      recommended_value: 40.0,
      potential_monthly_savings_usd: 35.0,
      reason: "EC2 instance t3.large CPU utilization is consistently low (8.0%).",
      recommendation: "Downsize instance from t3.large ($75.00/mo) to t3.medium ($40.00/mo). Potential saving: $35.00/month.",
      action: "HUMAN_APPROVAL_REQUIRED",
      evidence: {
        instance_type: "t3.large",
        cpu_utilization: "8.0%",
        current_monthly_cost: "$75.00/mo",
        target_instance: "t3.medium",
        target_monthly_cost: "$40.00/mo",
      },
      savings: {
        monthly_usd: 35.0,
        confidence: "high",
        calculation: "$75.00/month (t3.large) - $40.00/month (t3.medium)",
        evidence_available: true,
        assumptions: [
          "Current instance t3.large cost: $75.00/month.",
          "Target instance t3.medium cost: $40.00/month.",
          "Workload memory and peak CPU allow t3.medium footprint.",
        ],
      },
    },
    {
      domain: "kubernetes",
      resource_id: "cloudforge-dev/api-service",
      severity: "warning",
      metric: "cpu_request_vs_usage",
      observed_value: 8.0,
      recommended_value: 1.25,
      potential_monthly_savings_usd: 17.5,
      reason: "CPU request is substantially higher than observed CPU usage (2.0 cores requested vs 0.25 cores used).",
      recommendation: "Review CPU requests using representative peak/p95 workload data before reducing them. Potential saving: $17.50/month.",
      action: "HUMAN_APPROVAL_REQUIRED",
      evidence: {
        cpu_request_cores: 2.0,
        cpu_usage_cores: 0.25,
        replicas: 2,
      },
      savings: {
        monthly_usd: 17.5,
        confidence: "high",
        calculation: "(2.0 requested - 0.25 used) x $10.00/core/mo",
        evidence_available: true,
        assumptions: ["Recommended CPU request uses 1.25x observed usage."],
      },
    },
    {
      domain: "rds",
      resource_id: "db-cloudforge-prod (db.r5.xlarge)",
      severity: "warning",
      metric: "cpu_percent",
      observed_value: 12.4,
      recommended_value: 30.0,
      potential_monthly_savings_usd: 0.0,
      reason: "RDS CPU utilization is consistently low (12.4%) according to observed metrics.",
      recommendation: "Review instance class db.r5.xlarge and workload peak requirements before considering rightsizing.",
      action: "HUMAN_APPROVAL_REQUIRED",
      evidence: {
        instance_class: "db.r5.xlarge",
        cpu_percent: 12.4,
        monthly_cost_usd: 55.5,
      },
      savings: {
        monthly_usd: 0.0,
        confidence: "unknown",
        calculation: "Savings not estimated: explicit target class pricing evidence required.",
        evidence_available: false,
        assumptions: ["Review required by DevOps/Platform engineer."],
      },
    },
    {
      domain: "s3",
      resource_id: "cloudforge-app-bucket",
      severity: "info",
      metric: "object_count",
      observed_value: 142000,
      recommended_value: 100000,
      potential_monthly_savings_usd: 0.0,
      reason: "S3 bucket contains 142,000 objects without active lifecycle transition rules.",
      recommendation: "Review object age distribution and configure lifecycle transitions to S3 Standard-IA / Glacier.",
      action: "HUMAN_APPROVAL_REQUIRED",
      evidence: {
        object_count: 142000,
        storage_bytes: 42949672960,
      },
      savings: {
        monthly_usd: 0.0,
        confidence: "unknown",
        calculation: "Savings dependent on storage tier transition selection.",
        evidence_available: false,
        assumptions: ["S3 Standard to Standard-IA saves up to 40% per GB."],
      },
    },
  ],
  total_potential_monthly_savings_usd: 52.5,
  finding_count: 4,
};

const DEMO_REPORT: FinOpsReport = {
  region: "eu-west-1",
  account_id: "123456789012",
  resources: [
    { resource_id: "vpc-0a1b2c3d", resource_type: "VPC", service: "VPC", estimated_monthly_cost: 0.0, idle: false, tags: {}, region: "eu-west-1" },
    { resource_id: "i-0abcdef1234567890", resource_type: "EC2", service: "EC2", estimated_monthly_cost: 75.0, idle: false, tags: {}, region: "eu-west-1" },
    { resource_id: "i-0987654321fedcba", resource_type: "EC2", service: "EC2", estimated_monthly_cost: 10.4, idle: false, tags: {}, region: "eu-west-1" },
    { resource_id: "db-cloudforge-prod", resource_type: "RDS", service: "RDS", estimated_monthly_cost: 55.5, idle: false, tags: {}, region: "eu-west-1" },
    { resource_id: "cloudforge-cluster", resource_type: "EKS", service: "EKS", estimated_monthly_cost: 73.0, idle: false, tags: {}, region: "eu-west-1" },
    { resource_id: "app-alb", resource_type: "Load Balancer", service: "ELB", estimated_monthly_cost: 22.5, idle: false, tags: {}, region: "eu-west-1" },
    { resource_id: "cloudforge-app-bucket", resource_type: "S3", service: "S3", estimated_monthly_cost: 18.1, idle: false, tags: {}, region: "eu-west-1" },
  ],
};

const PRESET_EC2 = {
  plan: JSON.stringify({
    resource_changes: [
      {
        address: "aws_instance.web",
        mode: "managed",
        type: "aws_instance",
        name: "web",
        change: {
          actions: ["create"],
          before: null,
          after: { instance_type: "t3.micro", region: "eu-west-1" }
        }
      }
    ]
  }, null, 2),
  pricing: JSON.stringify({
    "aws_instance.web": {
      unit_monthly_usd: 10.4,
      source: "aws-standard-pricing",
      evidence_available: true,
      confidence: "high",
      assumptions: ["t3.micro in eu-west-1 on-demand ($0.0144/hr)"]
    }
  }, null, 2)
};

const PRESET_STACK = {
  plan: JSON.stringify({
    resource_changes: [
      {
        address: "aws_vpc.main",
        mode: "managed",
        type: "aws_vpc",
        name: "main",
        change: { actions: ["create"], before: null, after: { region: "eu-west-1" } }
      },
      {
        address: "aws_instance.web",
        mode: "managed",
        type: "aws_instance",
        name: "web",
        change: { actions: ["create"], before: null, after: { instance_type: "t3.micro", region: "eu-west-1" } }
      },
      {
        address: "aws_s3_bucket.storage",
        mode: "managed",
        type: "aws_s3_bucket",
        name: "storage",
        change: { actions: ["create"], before: null, after: { region: "eu-west-1" } }
      },
      {
        address: "aws_db_instance.db",
        mode: "managed",
        type: "aws_db_instance",
        name: "db",
        change: { actions: ["create"], before: null, after: { region: "eu-west-1" } }
      },
      {
        address: "aws_lb.ingress",
        mode: "managed",
        type: "aws_lb",
        name: "ingress",
        change: { actions: ["create"], before: null, after: { region: "eu-west-1" } }
      }
    ]
  }, null, 2),
  pricing: JSON.stringify({
    "aws_vpc.main": {
      unit_monthly_usd: 0,
      source: "aws-standard-pricing",
      evidence_available: true,
      confidence: "high",
      assumptions: ["VPC baseline is free"]
    },
    "aws_instance.web": {
      unit_monthly_usd: 10.4,
      source: "aws-standard-pricing",
      evidence_available: true,
      confidence: "high",
      assumptions: ["t3.micro on-demand"]
    },
    "aws_s3_bucket.storage": {
      unit_monthly_usd: 5.0,
      source: "aws-standard-pricing",
      evidence_available: true,
      confidence: "high",
      assumptions: ["Standard tier 50GB storage"]
    },
    "aws_db_instance.db": {
      unit_monthly_usd: 18.5,
      source: "aws-standard-pricing",
      evidence_available: true,
      confidence: "high",
      assumptions: ["db.t4g.micro with 20GB storage"]
    },
    "aws_lb.ingress": {
      unit_monthly_usd: 22.5,
      source: "aws-standard-pricing",
      evidence_available: true,
      confidence: "high",
      assumptions: ["Application Load Balancer baseline"]
    }
  }, null, 2)
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
  const [isDemoMode, setIsDemoMode] = useState(false);
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

    const [
      reportResult,
      historyResult,
      trendResult,
      anomalyResult,
      attributionResult,
      budgetsResult,
      optimizationResult,
    ] = results;

    const liveAvailable =
      (reportResult.status === "fulfilled" && Boolean(reportResult.value.account_id)) ||
      (budgetsResult.status === "fulfilled" && budgetsResult.value.budgets.length > 0) ||
      (historyResult.status === "fulfilled" && historyResult.value.points.length > 0) ||
      (reportResult.status === "fulfilled" && (reportResult.value.resources?.length ?? 0) > 0);

    if (liveAvailable) {
      if (reportResult.status === "fulfilled") setReport(reportResult.value);
      if (historyResult.status === "fulfilled") setHistory(historyResult.value);
      if (trendResult.status === "fulfilled") setTrend(trendResult.value);
      if (anomalyResult.status === "fulfilled") setAnomalies(anomalyResult.value);
      if (attributionResult.status === "fulfilled") setAttribution(attributionResult.value);
      if (budgetsResult.status === "fulfilled") setBudgets(budgetsResult.value);
      if (optimizationResult.status === "fulfilled") setOptimization(optimizationResult.value);
      setIsDemoMode(false);
      setError(null);
    } else {
      // Graceful demo mode fallback: Display full platform telemetry across 6 core AWS resources
      setReport(reportResult.status === "fulfilled" ? reportResult.value : DEMO_REPORT);
      setHistory(
        historyResult.status === "fulfilled" && historyResult.value.total_cost > 0
          ? historyResult.value
          : DEMO_HISTORY,
      );
      setTrend(
        trendResult.status === "fulfilled" && trendResult.value.current_cost > 0
          ? trendResult.value
          : DEMO_TREND,
      );
      setAnomalies(
        anomalyResult.status === "fulfilled" && anomalyResult.value.anomalies.length > 0
          ? anomalyResult.value
          : DEMO_ANOMALIES,
      );
      setAttribution(
        attributionResult.status === "fulfilled" && attributionResult.value.entries.length > 0
          ? attributionResult.value
          : DEMO_ATTRIBUTION,
      );
      setBudgets(
        budgetsResult.status === "fulfilled" && budgetsResult.value.budgets.length > 0
          ? budgetsResult.value
          : DEMO_BUDGETS,
      );
      setOptimization(
        optimizationResult.status === "fulfilled" && optimizationResult.value.findings.length > 0
          ? optimizationResult.value
          : DEMO_OPTIMIZATION,
      );
      setIsDemoMode(true);
      setError(null);
    }

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

          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
                isDemoMode
                  ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
                  : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  isDemoMode ? "bg-amber-500" : "bg-emerald-500"
                }`}
              />
              {isDemoMode ? "Demo Mode (Simulated AWS)" : `Live AWS · ${report?.account_id ?? "Connected"}`}
            </span>

            <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] px-3 py-2 text-xs text-[var(--cf-text-muted)]">
              {loading
                ? "Refreshing..."
                : `Updated ${lastUpdated ?? "just now"}`}
            </div>
          </div>
        </header>

        {isDemoMode && (
          <section className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-4">
            <div className="flex items-center gap-3">
              <span className="flex h-3 w-3 rounded-full bg-indigo-500 animate-pulse" />
              <div>
                <p className="text-sm font-semibold text-indigo-700 dark:text-indigo-300">
                  Demo Mode Active · AWS Telemetry Preview
                </p>
                <p className="mt-0.5 text-xs text-indigo-600 dark:text-indigo-200">
                  Live AWS credentials are not connected. Showing simulated FinOps telemetry across the 6 core resources (VPC, EC2, RDS, S3, EKS, ALB).
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void load()}
              className="self-start sm:self-auto rounded-lg border border-indigo-500/30 bg-indigo-500/20 px-3 py-1.5 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-500/30 dark:text-indigo-200"
            >
              Test Live AWS
            </button>
          </section>
        )}

        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
            Internal Developer Platform · FinOps Closed Loop
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3">
              <div className="flex items-center gap-2 text-xs font-bold text-[var(--cf-text)]">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-600 text-[10px]">1</span>
                Plan Cost Estimation
              </div>
              <p className="mt-1 text-xs text-[var(--cf-text-secondary)]">
                Pre-provisioning Terraform plan estimate before infrastructure mutate.
              </p>
            </div>
            <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3">
              <div className="flex items-center gap-2 text-xs font-bold text-[var(--cf-text)]">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-600 text-[10px]">2</span>
                AWS Actual Cost
              </div>
              <p className="mt-1 text-xs text-[var(--cf-text-secondary)]">
                Post-provisioning Cost Explorer tracking across all 6 core resources.
              </p>
            </div>
            <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3">
              <div className="flex items-center gap-2 text-xs font-bold text-[var(--cf-text)]">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-500/20 text-amber-600 text-[10px]">3</span>
                Resource Utilization
              </div>
              <p className="mt-1 text-xs text-[var(--cf-text-secondary)]">
                Prometheus cAdvisor telemetry (CPU %, memory %, request vs usage).
              </p>
            </div>
            <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3">
              <div className="flex items-center gap-2 text-xs font-bold text-[var(--cf-text)]">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-rose-500/20 text-rose-600 text-[10px]">4</span>
                Optimization Action
              </div>
              <p className="mt-1 text-xs text-[var(--cf-text-secondary)]">
                Evidence-based downsizing & rightsizing recommendations with human approval.
              </p>
            </div>
          </div>
        </section>

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
              optimization.total_potential_monthly_savings_usd,
            )}
            description="Evidence-based EC2 & Kubernetes optimization estimate."
          />
        </section>

        {/* ── Historical Cost Trend with SVG Sparkline ───────────────── */}
        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            <div>
              <h2 className="text-xl font-semibold">Cost trend</h2>
              <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
                Daily spend over the selected period · {history.start_date} – {history.end_date}
              </p>
            </div>
            <span
              className={`self-start rounded-full px-3 py-1 text-xs font-semibold uppercase ${
                trend.trend === "improving"
                  ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                  : trend.trend === "worsening"
                  ? "bg-rose-500/10 text-rose-700 dark:text-rose-300"
                  : "bg-sky-500/10 text-sky-700 dark:text-sky-300"
              }`}
            >
              {trend.trend === "improving" ? "↓ " : trend.trend === "worsening" ? "↑ " : "→ "}
              {trend.trend}
            </span>
          </div>

          {/* SVG sparkline area chart */}
          {history.points.length > 1 && (() => {
            const pts = history.points;
            const W = 600; const H = 80; const PAD = 6;
            const amounts = pts.map((p) => p.amount);
            const minA = Math.min(...amounts);
            const maxA = Math.max(...amounts);
            const range = maxA - minA || 1;
            const xs = pts.map((_, i) => PAD + (i / (pts.length - 1)) * (W - PAD * 2));
            const ys = pts.map((p) => H - PAD - ((p.amount - minA) / range) * (H - PAD * 2));
            const linePath = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x},${ys[i]}`).join(" ");
            const areaPath = `${linePath} L${xs[xs.length - 1]},${H - PAD} L${xs[0]},${H - PAD} Z`;
            return (
              <div className="mt-4 w-full overflow-hidden rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3">
                <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none" style={{ height: "80px" }}>
                  <defs>
                    <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#6366f1" stopOpacity="0.3" />
                      <stop offset="100%" stopColor="#6366f1" stopOpacity="0.01" />
                    </linearGradient>
                  </defs>
                  <path d={areaPath} fill="url(#sparkGrad)" />
                  <path d={linePath} fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  {xs.map((x, i) => (
                    <circle key={i} cx={x} cy={ys[i]} r="3" fill="#6366f1" />
                  ))}
                </svg>
                <div className="mt-1 flex justify-between text-[10px] text-[var(--cf-text-muted)]">
                  {pts.map((p) => (
                    <span key={p.date}>{p.date.slice(5)}</span>
                  ))}
                </div>
              </div>
            );
          })()}

          <div className="mt-4 grid grid-cols-3 gap-3">
            <Card
              title="Current period"
              value={money(trend.current_cost)}
              description="Selected window"
            />
            <Card
              title="Previous period"
              value={money(trend.previous_cost)}
              description="Prior equivalent window"
            />
            <Card
              title="Change"
              value={`${trend.change_amount >= 0 ? "+" : ""}${money(trend.change_amount)}`}
              description={`${percent(trend.change_percent)} period-over-period`}
            />
          </div>
        </section>

        {/* ── Cost Anomaly Detection ─────────────────────────────────── */}
        <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold">Cost anomaly detection</h2>
              <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
                Statistical deviations beyond {anomalies.threshold}σ from expected daily spend.
              </p>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold ${
                (anomalies.anomalies ?? []).length === 0
                  ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                  : "bg-rose-500/10 text-rose-700 dark:text-rose-300"
              }`}
            >
              {(anomalies.anomalies ?? []).length === 0
                ? "No anomalies"
                : `${(anomalies.anomalies ?? []).length} anomalies detected`}
            </span>
          </div>

          {(anomalies.anomalies ?? []).length === 0 ? (
            <div className="mt-5 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-700 dark:text-emerald-300">
              ✓ No cost anomalies detected in the selected period. Spend is within expected statistical bounds.
            </div>
          ) : (
            <div className="mt-4 space-y-3">
              {(anomalies.anomalies ?? []).map((anomaly, idx) => {
                const severity =
                  anomaly.score >= 4
                    ? { label: "Critical", cls: "bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/30" }
                    : anomaly.score >= 3
                    ? { label: "High", cls: "bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30" }
                    : { label: "Medium", cls: "bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/30" };
                const pct = anomaly.expected_amount > 0
                  ? ((anomaly.amount / anomaly.expected_amount - 1) * 100).toFixed(0)
                  : "—";
                return (
                  <div
                    key={`${anomaly.date}-${idx}`}
                    className={`rounded-lg border p-4 ${severity.cls}`}
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full border px-2 py-0.5 text-xs font-bold ${severity.cls}`}>
                            {severity.label}
                          </span>
                          <span className="text-sm font-semibold">{anomaly.date}</span>
                          <span className="text-xs opacity-70">Score: {anomaly.score.toFixed(1)}σ</span>
                        </div>
                        <p className="text-sm">
                          Daily spend{" "}
                          <strong>{money(anomaly.amount)}</strong> was{" "}
                          <strong>+{pct}%</strong> above expected{" "}
                          <strong>{money(anomaly.expected_amount)}</strong>.
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-base font-bold">+{money(anomaly.deviation)}</p>
                        <p className="text-xs opacity-70">over expected</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
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
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            <div>
              <h2 className="text-xl font-semibold">Cost attribution</h2>
              <p className="mt-1 text-sm text-[var(--cf-text-secondary)]">
                AWS spend breakdown by service · Total: {money(attribution.total_cost)}
              </p>
            </div>
            <span className="self-start rounded-full border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-3 py-1 text-xs text-[var(--cf-text-muted)]">
              {attribution.start_date} – {attribution.end_date}
            </span>
          </div>

          {(attribution.entries ?? []).length === 0 ? (
            <p className="mt-5 text-sm text-[var(--cf-text-muted)]">No attribution data returned.</p>
          ) : (() => {
            const entries = (attribution.entries ?? []).slice(0, 10);
            const maxAmount = Math.max(...entries.map((e) => e.amount), 1);
            const total = attribution.total_cost || entries.reduce((s, e) => s + e.amount, 0) || 1;
            const barColors = [
              "bg-indigo-500",
              "bg-violet-500",
              "bg-sky-500",
              "bg-emerald-500",
              "bg-amber-500",
              "bg-rose-500",
              "bg-pink-500",
              "bg-teal-500",
              "bg-orange-500",
              "bg-cyan-500",
            ];
            return (
              <div className="mt-5 space-y-3">
                {entries.map((entry, i) => {
                  const widthPct = (entry.amount / maxAmount) * 100;
                  const totalPct = ((entry.amount / total) * 100).toFixed(1);
                  return (
                    <div key={`${entry.dimension}-${entry.value}`} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{entry.value}</span>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-[var(--cf-text-muted)]">{totalPct}%</span>
                          <span className="w-20 text-right font-semibold tabular-nums">
                            {money(entry.amount, entry.currency)}
                          </span>
                        </div>
                      </div>
                      <div className="h-2.5 w-full overflow-hidden rounded-full bg-[var(--cf-surface-2)]">
                        <div
                          className={`h-full rounded-full ${barColors[i % barColors.length]} transition-all duration-700`}
                          style={{ width: `${widthPct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })()}
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
                    <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
                      <div className="space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded bg-indigo-500/10 px-2 py-0.5 text-xs font-semibold uppercase text-indigo-700 dark:text-indigo-300">
                            {recommendation.domain}
                          </span>
                          <span className="rounded bg-amber-500/10 px-2 py-0.5 text-xs font-semibold uppercase text-amber-700 dark:text-amber-300">
                            {recommendation.severity}
                          </span>
                          <span className="font-mono text-xs text-[var(--cf-text-muted)]">
                            {recommendation.resource_id}
                          </span>
                        </div>

                        <p className="font-medium text-sm text-[var(--cf-text)]">
                          {recommendation.recommendation}
                        </p>

                        {recommendation.reason && (
                          <p className="text-xs text-[var(--cf-text-secondary)]">
                            {recommendation.reason}
                          </p>
                        )}

                        {recommendation.evidence &&
                          Object.keys(recommendation.evidence).length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[var(--cf-text-muted)]">
                              {Object.entries(recommendation.evidence).map(
                                ([key, val]) => (
                                  <span
                                    key={key}
                                    className="rounded border border-[var(--cf-border)] bg-[var(--cf-surface)] px-1.5 py-0.5"
                                  >
                                    {key}: {String(val)}
                                  </span>
                                ),
                              )}
                            </div>
                          )}
                      </div>

                      <div className="shrink-0 text-right">
                        {recommendation.potential_monthly_savings_usd > 0 ? (
                          <div className="text-base font-bold text-emerald-600 dark:text-emerald-400">
                            Save {money(recommendation.potential_monthly_savings_usd)}/mo
                          </div>
                        ) : (
                          <div className="text-xs font-medium text-[var(--cf-text-muted)]">
                            Review Required
                          </div>
                        )}
                        <span className="mt-1 inline-block rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-600 dark:text-amber-300">
                          {recommendation.action}
                        </span>
                        {(() => {
                          // Closed loop: Monitor → Detect → Recommend → Provision/Modify.
                          // This only opens a pre-filled request; AWS is changed solely
                          // by a reviewed, hashed, human-approved Terraform plan.
                          const rightsizing = getRightsizingRequest(recommendation);

                          if (!rightsizing) {
                            return null;
                          }

                          return (
                            <div className="mt-2">
                              <Link
                                href={buildRightsizingHref(rightsizing)}
                                className="inline-block rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-indigo-500"
                              >
                                Apply Rightsizing →
                              </Link>
                              <p className="mt-1 text-[10px] text-[var(--cf-text-muted)]">
                                Opens a Terraform plan request for{" "}
                                {rightsizing.toInstanceType}
                              </p>
                            </div>
                          );
                        })()}
                      </div>
                    </div>
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

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-[var(--cf-text-secondary)]">
              Quick Test Presets:
            </span>
            <button
              type="button"
              onClick={() => {
                setTerraformPlan(PRESET_EC2.plan);
                setTerraformPricing(PRESET_EC2.pricing);
              }}
              className="rounded-md border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-2.5 py-1 text-xs font-medium text-[var(--cf-text)] transition hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400"
            >
              EC2 Instance ($10.40/mo)
            </button>
            <button
              type="button"
              onClick={() => {
                setTerraformPlan(PRESET_STACK.plan);
                setTerraformPricing(PRESET_STACK.pricing);
              }}
              className="rounded-md border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-2.5 py-1 text-xs font-medium text-[var(--cf-text)] transition hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400"
            >
              Multi-Tier Production Stack ($56.40/mo)
            </button>
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
