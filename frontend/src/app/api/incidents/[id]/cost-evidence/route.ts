import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/auth";
import { backendRequest } from "@/lib/dashboard-api";
import { serviceConfig } from "@/lib/server-config";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const session = await verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  const respond = (data: object, status = 200) => NextResponse.json(data, { status, headers: { "Cache-Control": "private, no-store" } });
  if (!session) return respond({ status: "denied" }, 401);
  if (session.role !== "sre" && session.role !== "platform-engineer") return respond({ status: "denied" }, 403);
  const { id } = await context.params;
  if (!uuid.test(id) || request.nextUrl.search) return respond({ status: "unavailable" }, 400);
  try {
    const incidentResponse = await backendRequest(session, "aiops", `${serviceConfig.aiops}/api/v1/incidents/${id}`);
    if (!incidentResponse.ok) return respond({ status: "unavailable" }, incidentResponse.status === 404 ? 404 : 503);
    const incident = await incidentResponse.json();
    const project = incident.labels?.["cloudforge:project-id"] ?? incident.labels?.project_id;
    const resource = incident.labels?.["cloudforge:resource-id"] ?? incident.labels?.resource_id;
    if (typeof project !== "string" || typeof resource !== "string" || !uuid.test(project) || !uuid.test(resource)) {
      return respond({ status: "unavailable", reason: "Incident has no project and resource identifiers." });
    }
    const response = await backendRequest(session, "finops",
      `${serviceConfig.finops}/api/v1/finops/projects/${project}/resources/${resource}/costs`);
    if (!response.ok) return respond({ status: "unavailable", reason: "Verified resource cost attribution unavailable." });
    const evidence = await response.json();
    if (evidence.project_id !== project || evidence.status !== "available") return respond({ status: "unavailable" });
    return respond({ status: "available", project_id: project, resource_id: resource, evidence,
      basis: "Incident identifiers match the attributed resource. Cost evidence does not establish incident causality." });
  } catch { return respond({ status: "unavailable" }, 503); }
}
