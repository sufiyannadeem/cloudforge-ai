import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/auth";
import { emptyReliability, RELIABILITY_QUERIES, reliabilityValues, type ReliabilityMetric } from "@/lib/platform-reliability";

export async function GET(request: NextRequest) {
  const session = await verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (!session) return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  if (!["platform-engineer", "sre"].includes(session.role)) return NextResponse.json({ error: "Operator access required" }, { status: 403 });
  if (request.nextUrl.search) return NextResponse.json({ error: "Metric scope is managed by the platform" }, { status: 400 });
  const rows = emptyReliability();
  const unavailable: string[] = [];
  await Promise.all((Object.keys(RELIABILITY_QUERIES) as ReliabilityMetric[]).map(async (metric) => {
    const { label, query } = RELIABILITY_QUERIES[metric];
    try {
      const url = new URL("/api/v1/query", process.env.PROMETHEUS_URL ?? "http://localhost:9090");
      url.searchParams.set("query", query);
      const response = await fetch(url, { cache: "no-store", redirect: "error", signal: AbortSignal.timeout(5000) });
      if (!response.ok) throw new Error("Metrics unavailable");
      const values = reliabilityValues(await response.json(), label);
      for (const row of rows) {
        const value = values.get(row.service) ?? null;
        row[metric] = metric === "scalingLimited" && value !== 0 && value !== 1 ? null : value;
      }
      if (values.size !== rows.length) unavailable.push(metric);
    } catch { unavailable.push(metric); }
  }));
  return NextResponse.json({ source: "prometheus_kube_state_metrics", namespace: "cloudforge", rows, unavailable }, { headers: { "Cache-Control": "private, no-store" } });
}
