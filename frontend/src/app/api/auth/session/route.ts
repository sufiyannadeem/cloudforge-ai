import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/auth";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const session = verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (!session) {
    return NextResponse.json({ authenticated: false }, { status: 401, headers: { "Cache-Control": "no-store" } });
  }
  return NextResponse.json(
    { authenticated: true, username: session.sub, role: session.role, csrfToken: session.csrf, expiresAt: session.exp },
    { headers: { "Cache-Control": "no-store" } },
  );
}
