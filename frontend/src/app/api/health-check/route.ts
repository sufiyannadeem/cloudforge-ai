import { NextResponse } from "next/server";
import { serviceConfig } from "@/lib/config";

export const dynamic = "force-dynamic";

interface HealthCheckResult {
  name: string;
  description: string;
  port: number;
  status: "healthy" | "unhealthy";
  latencyMs: number | null;
  error?: string;
}

interface HealthTarget {
  name: string;
  description: string;
  url: string;
  port: number;
}

const healthTargets: HealthTarget[] = [
  {
    name: "Project Service",
    description: "Project lifecycle management",
    url: `${serviceConfig.project}/health`,
    port: 8080,
  },
  {
    name: "Infrastructure Service",
    description: "Infrastructure resource management",
    url: `${serviceConfig.infrastructure}/health`,
    port: 8081,
  },
  {
    name: "Deployment Service",
    description: "Application deployment workflows",
    url: `${serviceConfig.deployment}/health`,
    port: 8082,
  },
  {
    name: "AI-Ops Service",
    description: "Incident intelligence and analysis",
    url: `${serviceConfig.aiops}/health`,
    port: 8090,
  },
  {
    name: "Prometheus",
    description: "Metrics collection and querying",
    url: "http://localhost:9090/-/healthy",
    port: 9090,
  },
  {
    name: "Grafana",
    description: "Observability dashboards",
    url: "http://localhost:3000/api/health",
    port: 3000,
  },
];

async function checkHealth(
  target: HealthTarget,
): Promise<HealthCheckResult> {
  const startedAt = performance.now();

  try {
    const response = await fetch(target.url, {
      method: "GET",
      cache: "no-store",
      signal: AbortSignal.timeout(3_000),
    });

    const latencyMs = Math.round(
      performance.now() - startedAt,
    );

    if (!response.ok) {
      return {
        name: target.name,
        description: target.description,
        port: target.port,
        status: "unhealthy",
        latencyMs,
        error: `HTTP ${response.status}`,
      };
    }

    return {
      name: target.name,
      description: target.description,
      port: target.port,
      status: "healthy",
      latencyMs,
    };
  } catch (error) {
    return {
      name: target.name,
      description: target.description,
      port: target.port,
      status: "unhealthy",
      latencyMs: null,
      error:
        error instanceof Error
          ? error.message
          : "Health check failed",
    };
  }
}

export async function GET() {
  const results = await Promise.all(
    healthTargets.map(checkHealth),
  );

  const healthyCount = results.filter(
    (result) => result.status === "healthy",
  ).length;

  return NextResponse.json({
    checkedAt: new Date().toISOString(),
    healthyCount,
    totalCount: results.length,
    services: results,
  });
}
