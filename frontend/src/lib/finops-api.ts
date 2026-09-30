import { apiGet, apiPost } from "@/lib/api";
import type {
  BudgetResponse,
  CostAnomalyResponse,
  CostAttributionResponse,
  CostHistoryResponse,
  CostTrendResponse,
  FinOpsReport,
  OptimizationReport,
  TerraformPlanCostEstimateResponse,
  TerraformPricingEvidenceRequest,
} from "@/types/finops";

const proxy = (path: string): string =>
  `/api/proxy/finops/api/v1/finops${path}`;

const terraformProxy = (path: string): string =>
  `/api/proxy/finops/api/v1/terraform${path}`;

export async function getFinOpsReport(): Promise<FinOpsReport> {
  return apiGet<FinOpsReport>(
    proxy("/aws/report"),
  );
}

export async function getCostHistory(
  days = 30,
): Promise<CostHistoryResponse> {
  return apiGet<CostHistoryResponse>(
    `${proxy("/aws/history")}?days=${days}`,
  );
}

export async function getCostTrend(
  days = 30,
): Promise<CostTrendResponse> {
  return apiGet<CostTrendResponse>(
    `${proxy("/aws/trends")}?days=${days}`,
  );
}

export async function getCostAnomalies(
  days = 30,
): Promise<CostAnomalyResponse> {
  return apiGet<CostAnomalyResponse>(
    `${proxy("/aws/anomalies")}?days=${days}`,
  );
}

export async function getCostAttribution(
  dimension = "service",
  days = 30,
): Promise<CostAttributionResponse> {
  const params = new URLSearchParams({
    dimension,
    days: String(days),
  });

  return apiGet<CostAttributionResponse>(
    `${proxy("/aws/attribution")}?${params.toString()}`,
  );
}

export async function getBudgets(): Promise<BudgetResponse> {
  return apiGet<BudgetResponse>(
    proxy("/aws/budgets"),
  );
}

export async function getKubernetesOptimization(): Promise<OptimizationReport> {
  return apiGet<OptimizationReport>(
    proxy("/optimization/kubernetes"),
  );
}

export async function getAllOptimization(): Promise<OptimizationReport> {
  return apiPost<OptimizationReport>(
    proxy("/optimization/all"),
  );
}

export async function estimateTerraformPlanCost(
  plan: Record<string, unknown>,
  pricing: Record<string, TerraformPricingEvidenceRequest> = {},
): Promise<TerraformPlanCostEstimateResponse> {
  return apiPost<TerraformPlanCostEstimateResponse>(
    terraformProxy("/plan-cost-estimate"),
    {
      plan,
      pricing,
    },
  );
}
