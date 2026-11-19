import { NextRequest } from "next/server";
import { proxyAIOpsTelemetry } from "@/lib/aiops-telemetry-proxy";

export function GET(request: NextRequest) {
  return proxyAIOpsTelemetry(request, "/api/v1/slo/summary", {
    service: "deployment-service",
  });
}
