import { NextRequest, NextResponse } from "next/server";

const AIOPS_URL =
  process.env.AIOPS_URL ?? "http://localhost:8090";

export async function GET(
  request: NextRequest,
): Promise<NextResponse> {
  const service =
    request.nextUrl.searchParams.get("service") ??
    "deployment-service";

  const windowMinutes =
    request.nextUrl.searchParams.get("window_minutes") ??
    "60";

  const stepSeconds =
    request.nextUrl.searchParams.get("step_seconds") ??
    "60";

  const url = new URL(
    "/api/v1/anomalies/summary",
    AIOPS_URL,
  );

  url.searchParams.set("service", service);
  url.searchParams.set("window_minutes", windowMinutes);
  url.searchParams.set("step_seconds", stepSeconds);

  try {
    const response = await fetch(url, {
      method: "GET",
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });

    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ??
          "application/json",
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Unable to reach AI-Ops service",
      },
      {
        status: 502,
      },
    );
  }
}
