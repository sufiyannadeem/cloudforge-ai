export interface PrometheusMetric {
  __name__?: string;
  environment?: string;
  instance?: string;
  job?: string;
  service?: string;
  method?: string;
  route?: string;
  status?: string;
  [key: string]: string | undefined;
}

export interface PrometheusSample {
  metric: PrometheusMetric;
  value: [number, string];
}

export interface PrometheusQueryData {
  resultType: "vector" | "matrix" | "scalar" | "string";
  result: PrometheusSample[];
}

export interface PrometheusQueryResponse {
  status: "success" | "error";
  data?: PrometheusQueryData;
  errorType?: string;
  error?: string;
}

export interface ObservabilitySummary {
  availability: number | null;
  requestRate: number | null;
  errorRate: number | null;
  p95Latency: number | null;
  deploymentsInProgress: number | null;
  requestsInFlight: number | null;
}
