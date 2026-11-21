import { NextRequest, NextResponse } from "next/server";
import { pageDecision } from "@/lib/role-access";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/auth";

export async function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  if (
    pathname === "/login" ||
    pathname.startsWith("/api/auth/") ||
    pathname.startsWith("/api/proxy/") ||
    pathname.startsWith("/_next/") ||
    pathname === "/favicon.ico"
  ) {
    return NextResponse.next();
  }

  const session = await verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (pathname.startsWith("/api/")) {
    if (!session) {
      return NextResponse.json({ error: { message: "Authentication required" } },
        { status: 401, headers: { "Cache-Control": "no-store" } });
    }
    if (session.role === "developer" && pathname === "/api/health-check") {
      return NextResponse.json({ error: { message: "Operator permission required" } }, { status: 403 });
    }
    return NextResponse.next();
  }

  const decision = pageDecision(session?.role ?? null, pathname);
  if (decision === "allow") return NextResponse.next();
  if (decision === "deny") {
    return NextResponse.rewrite(new URL("/access-denied", request.url), {
      status: 403, headers: { "Cache-Control": "no-store" },
    });
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", `${pathname}${request.nextUrl.search}`);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
