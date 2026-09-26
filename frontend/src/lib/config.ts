const getRequiredEnv = (name: string, fallback: string): string => {
  const value = process.env[name];

  if (!value || value.trim().length === 0) {
    return fallback;
  }

  return value;
};

const getTimeout = (): number => {
  const value = Number(process.env.API_REQUEST_TIMEOUT_MS);

  if (!Number.isFinite(value) || value <= 0) {
    return 10_000;
  }

  return value;
};

export const appConfig = {
  name: getRequiredEnv("NEXT_PUBLIC_APP_NAME", "CloudForge AI"),
  environment: getRequiredEnv("NEXT_PUBLIC_APP_ENV", "development"),
  requestTimeoutMs: getTimeout(),
} as const;

export const serviceConfig = {
  project: getRequiredEnv(
    "PROJECT_SERVICE_URL",
    "http://localhost:8080",
  ),
  infrastructure: getRequiredEnv(
    "INFRASTRUCTURE_SERVICE_URL",
    "http://localhost:8081",
  ),
  deployment: getRequiredEnv(
    "DEPLOYMENT_SERVICE_URL",
    "http://localhost:8082",
  ),
  aiops: getRequiredEnv(
    "AIOPS_SERVICE_URL",
    "http://localhost:8090",
  ),
} as const;
