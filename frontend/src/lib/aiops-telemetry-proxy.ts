import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/auth";
import { backendRequest } from "@/lib/dashboard-api";
import { serviceConfig } from "@/lib/server-config";

export async function proxyAIOpsTelemetry(
  request: NextRequest,
  path: "/api/v1/slo/summary" | "/api/v1/anomalies/summary",
  defaults: Record<string, string>,
) {
  const headers = { "Cache-Control": "private, no-store" };
  const session = await verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (!session) return NextResponse.json({ detail: "Authentication required" }, { status: 401, headers });
  if (session.role === "developer") {
    return NextResponse.json({ detail: "Operator permission required" }, { status: 403, headers });
  }

  const url = new URL(path, serviceConfig.aiops);
  for (const [key, fallback] of Object.entries(defaults)) {
    url.searchParams.set(key, request.nextUrl.searchParams.get(key) ?? fallback);
  }
  try {
    const response = await backendRequest(session, "aiops", url.toString(), 25_000);
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { ...headers, "Content-Type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "Unable to reach AIOps service" }, { status: 502, headers });
  }
}
