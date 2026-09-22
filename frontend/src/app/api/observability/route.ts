import { NextRequest, NextResponse } from "next/server";

const PROMETHEUS_URL =
  process.env.PROMETHEUS_URL ?? "http://localhost:9090";

const REQUEST_TIMEOUT_MS = 10_000;

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("query");

  if (!query?.trim()) {
    return NextResponse.json(
      {
        error: "The query parameter is required.",
      },
      { status: 400 },
    );
  }

  const url = new URL("/api/v1/query", PROMETHEUS_URL);
  url.searchParams.set("query", query);

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });

    const body = await response.json();

    if (!response.ok) {
      return NextResponse.json(body, {
        status: response.status,
      });
    }

    return NextResponse.json(body, {
      status: 200,
    });
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Unable to connect to Prometheus.";

    return NextResponse.json(
      {
        error: "Prometheus query failed.",
        details: message,
      },
      { status: 502 },
    );
  }
}
