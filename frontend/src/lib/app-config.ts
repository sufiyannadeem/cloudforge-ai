const getOptionalEnv = (name: string, fallback: string): string => {
  const value = process.env[name];

  if (!value || value.trim().length === 0) {
    return fallback;
  }

  return value;
};

const getTimeout = (): number => {
  const value = Number(process.env.NEXT_PUBLIC_API_REQUEST_TIMEOUT_MS);

  if (!Number.isFinite(value) || value <= 0) {
    return 10_000;
  }

  return value;
};

export const appConfig = {
  name: getOptionalEnv("NEXT_PUBLIC_APP_NAME", "CloudForge AI"),
  environment: getOptionalEnv("NEXT_PUBLIC_APP_ENV", "development"),
  requestTimeoutMs: getTimeout(),
} as const;
