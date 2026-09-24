export type AnomalyClassification =
  | "normal"
  | "anomaly"
  | "critical"
  | "insufficient_data";

export type AnomalyDirection =
  | "stable"
  | "increase"
  | "decrease";

export interface AnomalyMetric {
  name: string;
  display_name: string;
  unit: string;
  current_value: number | null;
  baseline_value: number | null;
  standard_deviation: number | null;
  z_score: number | null;
  deviation_percent: number | null;
  direction: AnomalyDirection;
  classification: AnomalyClassification;
  evidence: string[];
  sample_count: number;
  evaluated_at: string;
}

export interface AnomalySummary {
  service: string;
  window_minutes: number;
  step_seconds: number;
  overall_classification: AnomalyClassification;
  normal_count: number;
  anomaly_count: number;
  critical_count: number;
  insufficient_data_count: number;
  metrics: AnomalyMetric[];
  generated_at: string;
}
