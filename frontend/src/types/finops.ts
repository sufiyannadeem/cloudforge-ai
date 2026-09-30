export interface CostHistoryPoint {
  date: string;
  amount: number;
  currency: string;
}

export interface CostHistoryResponse {
  start_date: string;
  end_date: string;
  total_cost: number;
  average_daily_cost: number;
  points: CostHistoryPoint[];
}

export interface CostTrendResponse {
  start_date: string;
  end_date: string;
  comparison_start_date: string;
  comparison_end_date: string;
  current_cost: number;
  previous_cost: number;
  change_amount: number;
  change_percent: number | null;
  trend: string;
  currency: string;
}

export interface CostAnomaly {
  date: string;
  amount: number;
  expected_amount: number;
  deviation: number;
  score: number;
}

export interface CostAnomalyResponse {
  start_date: string;
  end_date: string;
  threshold: number;
  anomalies: CostAnomaly[];
}

export interface CostAttributionEntry {
  dimension: string;
  value: string;
  amount: number;
  currency: string;
}

export interface CostAttributionResponse {
  start_date: string;
  end_date: string;
  dimension: string;
  tag_key?: string;
  total_cost: number;
  entries: CostAttributionEntry[];
}

export interface BudgetSummary {
  name: string;
  budget_type: string;
  time_unit: string;
  limit: number | null;
  actual_spend: number | null;
  forecasted_spend: number | null;
  currency: string;
  actual_utilization_percent: number | null;
  forecast_utilization_percent: number | null;
  status: string;
  cost_filters: Record<string, unknown>;
}

export interface BudgetResponse {
  account_id: string;
  budgets: BudgetSummary[];
}

export interface FinOpsResource {
  resource_id: string;
  resource_type: string;
  service: string;
  estimated_monthly_cost: number;
  idle: boolean;
  tags: Record<string, string>;
  region: string;
}

export interface FinOpsReport {
  region: string;
  account_id?: string | null;
  resources: FinOpsResource[];
  cost_data_source?: string;
}

export interface SavingsEvidence {
  monthly_usd: number;
  confidence: string;
  calculation: string;
  pricing_source?: string | null;
  assumptions: string[];
  evidence_available: boolean;
}

export interface OptimizationFinding {
  domain: string;
  resource_id: string;
  severity: string;
  metric: string;
  observed_value?: number | null;
  recommended_value?: number | null;
  potential_monthly_savings_usd: number;
  savings: SavingsEvidence;
  reason: string;
  recommendation: string;
  action: string;
  evidence: Record<string, unknown>;
}

export interface OptimizationReport {
  generated_by: string;
  findings: OptimizationFinding[];
  total_potential_monthly_savings_usd: number;
  finding_count: number;
}

export interface TerraformCostEstimate {
  resource_type: string;
  resource_id: string;
  action: string;
  region: string;
  current_monthly_usd: number;
  proposed_monthly_usd: number;
  monthly_delta_usd: number;
  pricing_source?: string | null;
  confidence: string;
  evidence_available: boolean;
  calculation: string;
  assumptions: string[];
}

export interface TerraformCostEstimateReport {
  estimates: TerraformCostEstimate[];
  total_current_monthly_usd: number;
  total_proposed_monthly_usd: number;
  total_monthly_delta_usd: number;
  evidence_complete: boolean;
  resource_count: number;
  generated_by: string;
}

export interface TerraformPlanCostEstimateResponse {
  cost_report: TerraformCostEstimateReport;
  parse_issues: string[];
  unsupported_resources: string[];
  parsed_resource_count: number;
}

export interface TerraformPricingEvidenceRequest {
  unit_monthly_usd: number;
  source: string;
  evidence_available?: boolean;
  confidence?: string;
  assumptions?: string[];
}
