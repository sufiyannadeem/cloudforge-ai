import { NextRequest, NextResponse } from "next/server";
import { serviceConfig } from "@/lib/server-config";
import {
  CSRF_COOKIE,
  internalApiToken,
  originMatchesRequest,
  SESSION_COOKIE,
  verifySessionToken,
} from "@/lib/auth";

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
  role: string,
  service: SupportedService,
  path: string[],
  method: string,
): boolean {
  if (role === "admin") return true;
  if (!MUTATING_METHODS.has(method)) return true;
  if (role === "viewer") return false;

  if (service === "finops") {
    return ["platform-engineer", "devops", "sre"].includes(role);
  }

  if (service === "infrastructure") {
    const joinedPath = path.join("/");
    const highRiskMutation =
      method === "DELETE" ||
      joinedPath.endsWith("/apply") ||
      joinedPath.endsWith("/destroy/apply");
    if (highRiskMutation) return role === "platform-engineer";
    return ["platform-engineer", "devops", "sre"].includes(role);
  }

  if (service === "deployment") {
    if (method === "DELETE") return role === "platform-engineer";
    return ["platform-engineer", "devops", "sre"].includes(role);
  }

  return ["platform-engineer", "devops", "sre"].includes(role);
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

  const session = verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (!session) {
    return createErrorResponse("Authentication required", 401);
  }

  const serviceToken = internalApiToken();
  if (!serviceToken) {
    return createErrorResponse("Backend authentication is not configured", 503);
  }

  if (!isAuthorizedForRoute(session.role, service, path, request.method)) {
    return createErrorResponse("Insufficient permissions for this operation", 403);
  }

  if (MUTATING_METHODS.has(request.method)) {
    const csrfCookie = request.cookies.get(CSRF_COOKIE)?.value;
    const csrfHeader = request.headers.get("x-csrf-token");
    const csrfChecks = {
      originMatches: originMatchesRequest(
        request.headers.get("origin"),
        request.url,
        request.headers.get("host"),
      ),
      sessionHasCsrf: Boolean(session.csrf),
      cookieMatchesSession: Boolean(csrfCookie && csrfCookie === session.csrf),
      headerMatchesSession: Boolean(csrfHeader && csrfHeader === session.csrf),
    };

    if (Object.values(csrfChecks).some((passed) => !passed)) {
      console.warn("[CloudForge CSRF] Validation failed", {
        method: request.method,
        service,
        checks: csrfChecks,
      });
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

  request.nextUrl.searchParams.forEach((value, key) => {
    targetUrl.searchParams.append(key, value);
  });

  const headers = new Headers();
  headers.set("X-CloudForge-Internal-Token", serviceToken);
  headers.set("X-CloudForge-Actor", session.sub);
  headers.set("X-CloudForge-Role", session.role);

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

  const isProvisioningOperation =
    service === "infrastructure" &&
    path.some((segment) => segment === "plan" || segment === "apply");
  const requestTimeoutMs = isProvisioningOperation ? 600_000 : 10_000;

  try {
    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(requestTimeoutMs),
    });

    const responseHeaders = new Headers();

    const responseContentType =
      response.headers.get("content-type");

    if (responseContentType) {
      responseHeaders.set(
        "content-type",
        responseContentType,
      );
    }

    const responseBody = await response.arrayBuffer();

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
