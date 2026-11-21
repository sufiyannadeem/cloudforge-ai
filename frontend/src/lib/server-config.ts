import "server-only";

const getServiceUrl = (name: string, localFallback: string): string => {
  const value = process.env[name];

  if (value && value.trim().length > 0) {
    return value;
  }

  const isBuildPhase = process.env.NEXT_PHASE === "phase-production-build";

  if (process.env.NODE_ENV === "production" && !isBuildPhase) {
    throw new Error(
      `Missing required environment variable "${name}" in production`,
    );
  }

  return localFallback;
};

export const serviceConfig = {
  project: getServiceUrl("PROJECT_SERVICE_URL", "http://localhost:8080"),
  infrastructure: getServiceUrl("INFRASTRUCTURE_SERVICE_URL", "http://localhost:8081"),
  deployment: getServiceUrl("DEPLOYMENT_SERVICE_URL", "http://localhost:8082"),
  aiops: getServiceUrl("AIOPS_SERVICE_URL", "http://localhost:8090"),
  finops: getServiceUrl("FINOPS_SERVICE_URL", "http://localhost:8091"),
  prometheus: getServiceUrl("PROMETHEUS_URL", "http://localhost:9090"),
  grafana: getServiceUrl("GRAFANA_URL", "http://localhost:3001"),
} as const;
