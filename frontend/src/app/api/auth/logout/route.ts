import { NextRequest, NextResponse } from "next/server";
import { CSRF_COOKIE, revokeSession, SESSION_COOKIE, sessionCSRF } from "@/lib/auth";
import { matchesCSRF, originMatchesRequest, secureAuthCookies } from "@/lib/csrf";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (
    !originMatchesRequest(
      origin,
      request.url,
      request.headers.get("host"),
    )
  ) {
    return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!matchesCSRF(sessionCSRF(token), request.cookies.get(CSRF_COOKIE)?.value, request.headers.get("x-csrf-token"))) {
    return NextResponse.json({ error: "Invalid session or CSRF token" }, { status: 403 });
  }
  if (!await revokeSession(token)) {
    return NextResponse.json({ error: "Session revocation unavailable" }, { status: 503 });
  }
  const secure = secureAuthCookies(origin);
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, secure, sameSite: "lax", path: "/", maxAge: 0 });
  response.cookies.set(CSRF_COOKIE, "", { httpOnly: false, secure, sameSite: "strict", path: "/", maxAge: 0 });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
