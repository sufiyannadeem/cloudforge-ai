import { NextRequest, NextResponse } from "next/server";
import { CSRF_COOKIE, originMatchesRequest, SESSION_COOKIE, verifySessionToken } from "@/lib/auth";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  if (
    !originMatchesRequest(
      request.headers.get("origin"),
      request.url,
      request.headers.get("host"),
    )
  ) {
    return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
  }
  const session = verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (!session || request.headers.get("x-csrf-token") !== session.csrf ||
      request.cookies.get(CSRF_COOKIE)?.value !== session.csrf) {
    return NextResponse.json({ error: "Invalid session or CSRF token" }, { status: 403 });
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, secure: process.env.CLOUDFORGE_AUTH_COOKIE_SECURE !== "false", sameSite: "lax", path: "/", maxAge: 0 });
  response.cookies.set(CSRF_COOKIE, "", { httpOnly: false, secure: process.env.CLOUDFORGE_AUTH_COOKIE_SECURE !== "false", sameSite: "strict", path: "/", maxAge: 0 });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
