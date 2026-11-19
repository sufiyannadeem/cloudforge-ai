import { NextRequest } from "next/server";
import { proxyAIOpsTelemetry } from "@/lib/aiops-telemetry-proxy";

export function GET(request: NextRequest) {
  return proxyAIOpsTelemetry(request, "/api/v1/anomalies/summary", {
    service: "deployment-service",
    window_minutes: "60",
    step_seconds: "60",
  });
}
