import { NextRequest, NextResponse } from "next/server";
import {
  createSessionToken,
  credentialsMatch,
  CSRF_COOKIE,
  getAuthConfig,
  internalApiToken,
  originMatchesRequest,
  safeNextPath,
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
} from "@/lib/auth";

export const runtime = "nodejs";

const attempts = new Map<string, { count: number; resetAt: number }>();
const WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 10;

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

  const config = getAuthConfig();
  if (!config || !internalApiToken()) {
    return NextResponse.json(
      { error: "Authentication is not configured. Set the required server-side CloudForge auth settings." },
      { status: 503 },
    );
  }

  const now = Date.now();
  if (attempts.size > 10_000) {
    for (const [attemptKey, attempt] of attempts) {
      if (attempt.resetAt <= now) attempts.delete(attemptKey);
    }
  }
  const key = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
  const current = attempts.get(key);
  if (current && current.resetAt > now && current.count >= MAX_ATTEMPTS) {
    return NextResponse.json({ error: "Too many login attempts. Try again later." }, { status: 429 });
  }
  if (!current || current.resetAt <= now) {
    attempts.set(key, { count: 1, resetAt: now + WINDOW_MS });
  } else {
    current.count += 1;
  }

  let body: unknown;
  try {
    if (Number(request.headers.get("content-length") ?? "0") > 4096) {
      return NextResponse.json({ error: "Request too large" }, { status: 413 });
    }
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "Invalid login request" }, { status: 400 });
  }
  const input = body as Record<string, unknown>;
  const username = typeof input.username === "string" ? input.username : "";
  const password = typeof input.password === "string" ? input.password : "";

  if (!credentialsMatch(username, password, config)) {
    return NextResponse.json({ error: "Invalid username or password" }, { status: 401 });
  }

  attempts.delete(key);
  const { token, session } = createSessionToken(config.username, config.role, config.secret);
  const response = NextResponse.json({ ok: true, redirectTo: safeNextPath(typeof input.next === "string" ? input.next : null) });
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: config.cookieSecure,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  response.cookies.set(CSRF_COOKIE, session.csrf, {
    httpOnly: false,
    secure: config.cookieSecure,
    sameSite: "strict",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
