import { NextRequest, NextResponse } from "next/server";
import { serviceConfig } from "@/lib/config";

type SupportedService =
  | "project"
  | "infrastructure"
  | "deployment"
  | "aiops";

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
  return service in serviceUrls;
};

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

  try {
    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
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
