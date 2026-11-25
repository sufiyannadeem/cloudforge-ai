import { NextRequest, NextResponse } from "next/server";
import { serviceAssertion } from "@/lib/service-identity";
import { serviceConfig } from "@/lib/server-config";
import {
  type CloudForgeRole,
  CSRF_COOKIE,
  SESSION_COOKIE,
  verifySessionToken,
} from "@/lib/auth";
import { matchesCSRF, originMatchesRequest } from "@/lib/csrf";

type SupportedService =
  | "project"
  | "infrastructure"
  | "deployment"
  | "aiops"
  | "finops";

interface RouteContext {
  params: Promise<{
    service: string;
    path: string[];
  }>;
}

const serviceUrls: Record<SupportedService, string> = {
  project: serviceConfig.project,
  infrastructure: serviceConfig.infrastructure,
  deployment: serviceConfig.deployment,
  aiops: serviceConfig.aiops,
  finops: serviceConfig.finops,
};

const allowedMethods = new Set([
  "GET",
  "POST",
  "PATCH",
  "PUT",
  "DELETE",
]);

const isSupportedService = (
  service: string,
): service is SupportedService => {
  return Object.hasOwn(serviceUrls, service);
};

const MUTATING_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);

function isAuthorizedForRoute(
  role: CloudForgeRole,
  service: SupportedService,
  method: string,
  path: string[],
): boolean {
  if (service === "project" && path[0] === "admin") return role === "platform-engineer";
  if (service === "aiops" && role === "developer") return false;
  if (service === "finops" && role === "developer" && path[3] === "aws") return false;
  if (!MUTATING_METHODS.has(method)) return true;
  if (service === "aiops" && path.includes("remediation") && ["approve", "execute"].includes(path.at(-1) ?? "")) {
    return role === "platform-engineer";
  }

  if (service === "infrastructure") {
    if (method === "POST" && path.length === 5 && path[2] === "resources" && path[4] === "drift") {
      return role === "platform-engineer" || role === "sre";
    }
    return role === "platform-engineer" || (role === "developer" && method === "POST" &&
      (path.join("/") === "api/v1/resources" ||
        (path.length === 5 && path[2] === "resources" && (path[4] === "plan" || path[4] === "review"))));
  }
  if (service === "project") return path[0] !== "admin" || role === "platform-engineer";

  if (service === "deployment") {
    if (path.at(-1) === "promote") return role === "platform-engineer";
    return method !== "DELETE" || role === "platform-engineer";
  }

  return role !== "developer";
}

const createErrorResponse = (
  message: string,
  status: number,
) => {
  return NextResponse.json(
    {
      error: {
        message,
      },
    },
    { status },
  );
};

async function proxyRequest(
  request: NextRequest,
  context: RouteContext,
): Promise<NextResponse> {
  const { service, path } = await context.params;

  if (!isSupportedService(service)) {
    return createErrorResponse(
      "Unsupported backend service",
      404,
    );
  }

  if (!allowedMethods.has(request.method)) {
    return createErrorResponse(
      "HTTP method not allowed",
      405,
    );
  }

  const session = await verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (!session) {
    return createErrorResponse("Authentication required", 401);
  }

  if (!isAuthorizedForRoute(session.role, service, request.method, path)) {
    return createErrorResponse("Insufficient permissions for this operation", 403);
  }

  if (MUTATING_METHODS.has(request.method)) {
    const originMatches = originMatchesRequest(request.headers.get("origin"), request.url, request.headers.get("host"));
    const csrfMatches = matchesCSRF(session.csrf, request.cookies.get(CSRF_COOKIE)?.value, request.headers.get("x-csrf-token"));
    if (!originMatches || !csrfMatches) {
      return createErrorResponse("CSRF validation failed", 403);
    }
  }

  const serviceUrl = serviceUrls[service];

  const targetPath = path
    .map((segment) => encodeURIComponent(segment))
    .join("/");

  const targetUrl = new URL(
    `${serviceUrl.replace(/\/$/, "")}/${targetPath}`,
  );

  if (service === "project" && !/^\/projects(?:\/|$)/.test(targetUrl.pathname) && targetUrl.pathname !== "/admin/accounts") {
    return createErrorResponse("Unsupported project service route", 404);
  }

  request.nextUrl.searchParams.forEach((value, key) => {
    targetUrl.searchParams.append(key, value);
  });

  const headers = new Headers();
  const contentType = request.headers.get("content-type");

  if (contentType) {
    headers.set("content-type", contentType);
  }

  const accept = request.headers.get("accept");

  if (accept) {
    headers.set("accept", accept);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);

  let body: ArrayBuffer | undefined;

  if (hasBody) {
    body = await request.arrayBuffer();
  }

  const approvalBody = request.method === "POST" && ((service === "infrastructure" && /\/(apply|review)$/.test(targetUrl.pathname)) || (service === "project" && targetUrl.pathname === "/admin/accounts") || (service === "deployment" && /\/promote$/.test(targetUrl.pathname)) || (service === "aiops" && /\/remediation(?:\/|$)/.test(targetUrl.pathname)))
    ? body ?? new ArrayBuffer(0)
    : undefined;
  try {
    headers.set("X-CloudForge-Identity", serviceAssertion(service, targetUrl, request.method, session, approvalBody));
  } catch {
    return createErrorResponse("Backend identity is not configured", 503);
  }

  const isProvisioningOperation =
    service === "infrastructure" &&
    path.some((segment) => segment === "plan" || segment === "apply" || (request.method === "POST" && segment === "drift"));
  const isDeploymentTelemetry = service === "deployment" && request.method === "GET" &&
    path[2] === "deployments" && path.length === 5 && ["logs", "observability"].includes(path[4]);
  const isDiagnosticCapture = service === "deployment" && request.method === "POST" &&
    path[2] === "deployments" && path.length === 5 && path[4] === "diagnostics";
  const isAIAnalysis = service === "aiops" && request.method === "POST" &&
    /^\/api\/v1\/incidents\/[^/]+\/analyze$/.test(targetUrl.pathname);
  const requestTimeoutMs = isAIAnalysis ? 23_000 : isProvisioningOperation ? 23_000 : isDiagnosticCapture ? 23_000 : isDeploymentTelemetry ? 15_000 : 10_000;

  try {
    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(requestTimeoutMs),
    });

    const responseHeaders = new Headers({ "Cache-Control": "private, no-store" });

    const responseContentType =
      response.headers.get("content-type");

    if (responseContentType) {
      responseHeaders.set(
        "content-type",
        responseContentType,
      );
    }

    const responseBody = [204, 205, 304].includes(response.status) ? null : await response.arrayBuffer();

    return new NextResponse(responseBody, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("Backend proxy request failed", {
      service,
      targetPath,
      method: request.method,
      error:
        error instanceof Error
          ? error.message
          : "Unknown error",
    });

    return createErrorResponse(
      "Backend service is unavailable",
      503,
    );
  }
}

export async function GET(
  request: NextRequest,
  context: RouteContext,
) {
  return proxyRequest(request, context);
}

export async function POST(
  request: NextRequest,
  context: RouteContext,
) {
  return proxyRequest(request, context);
}

export async function PATCH(
  request: NextRequest,
  context: RouteContext,
) {
  return proxyRequest(request, context);
}

export async function PUT(
  request: NextRequest,
  context: RouteContext,
) {
  return proxyRequest(request, context);
}

export async function DELETE(
  request: NextRequest,
  context: RouteContext,
) {
  return proxyRequest(request, context);
}
