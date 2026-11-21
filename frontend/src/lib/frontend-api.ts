import type { TerraformDriftScan } from "@/types/infrastructure";
import type { DiagnosticCapture } from "@/types/deployments";
import type {
  CreateInfrastructureInput,
  CreateProjectInput,
  Deployment,
  DeploymentListResponse,
  InfrastructureListResponse,
  InfrastructureResource,
  Project,
  ProjectListResponse,
} from "@/types/api";

const readCookie = (name: string): string | undefined => {
  if (typeof document === "undefined") return undefined;
  const prefix = `${name}=`;
  const entry = document.cookie.split(";").map((item) => item.trim())
    .find((item) => item.startsWith(prefix));
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : undefined;
};

export const frontendApiRequest = async <T>(
  path: string,
  options: RequestInit = {},
): Promise<T> => {
  const csrfToken = readCookie("cf_csrf");
  const isMutation = Boolean(options.method && options.method.toUpperCase() !== "GET");
  const response = await fetch(path, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body
        ? { "Content-Type": "application/json" }
        : {}),
      ...(isMutation && csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      ...options.headers,
    },
    cache: "no-store",
  });

  const contentType =
    response.headers.get("content-type") ?? "";

  const body = contentType.includes("application/json")
    ? await response.json()
    : null;

  if (!response.ok) {
    const message =
      typeof body?.error?.message === "string"
        ? body.error.message
        : `Request failed with status ${response.status}`;

    throw new Error(message);
  }

  return body as T;
};

export const frontendApi = {
  projects: {
    observability: (id: string) =>
      frontendApiRequest<{ project_id: string; deployments_by_status: Record<string, number> }>(
        `/api/proxy/project/projects/${encodeURIComponent(id)}/observability`,
      ),
    list: () =>
      frontendApiRequest<ProjectListResponse>(
        "/api/proxy/project/projects",
      ),

    create: (payload: CreateProjectInput) =>
      frontendApiRequest<Project>(
        "/api/proxy/project/projects",
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
  },

  infrastructure: {
    driftHistory: (id: string) => frontendApiRequest<TerraformDriftScan[]>(
      `/api/proxy/infrastructure/api/v1/resources/${encodeURIComponent(id)}/drift`,
    ),
    scanDrift: (id: string) => frontendApiRequest<TerraformDriftScan>(
      `/api/proxy/infrastructure/api/v1/resources/${encodeURIComponent(id)}/drift`, { method: "POST" },
    ),

    list: () =>
      frontendApiRequest<InfrastructureListResponse>(
        "/api/proxy/infrastructure/api/v1/resources",
      ),

    create: (payload: CreateInfrastructureInput) =>
      frontendApiRequest<InfrastructureResource>(
        "/api/proxy/infrastructure/api/v1/resources",
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
  },

  deployments: {
    diagnostics: (id: string, signal?: AbortSignal) => frontendApiRequest<DiagnosticCapture[]>(
      `/api/proxy/deployment/api/v1/deployments/${encodeURIComponent(id)}/diagnostics`, { signal },
    ),
    captureDiagnostic: (id: string) => frontendApiRequest<DiagnosticCapture>(
      `/api/proxy/deployment/api/v1/deployments/${encodeURIComponent(id)}/diagnostics`, { method: "POST" },
    ),
    list: () =>
      frontendApiRequest<DeploymentListResponse>(
        "/api/proxy/deployment/api/v1/deployments",
      ),

    get: (deploymentId: string) =>
      frontendApiRequest<Deployment>(
        `/api/proxy/deployment/api/v1/deployments/${encodeURIComponent(
          deploymentId,
        )}`,
      ),
  },
};
