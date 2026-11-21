import { NextRequest, NextResponse } from "next/server";
import {
  authenticateAccount,
  CSRF_COOKIE,
  safeNextPath,
  SESSION_COOKIE,
} from "@/lib/auth";
import { originMatchesRequest, secureAuthCookies } from "@/lib/csrf";
import { dashboardDestination } from "@/lib/role-access";

export const runtime = "nodejs";

const attempts = new Map<string, { count: number; resetAt: number }>();
const WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 10;

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (!originMatchesRequest(origin, request.url, request.headers.get("host"))) {
    return NextResponse.json({ error: "Invalid request origin" }, { status: 403 });
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
    const reader = request.body?.getReader();
    const buffer = new Uint8Array(4096);
    let size = 0;
    if (reader) {
      for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) {
        if (size + chunk.value.length > buffer.length) {
          await reader.cancel();
          return NextResponse.json({ error: "Request too large" }, { status: 413 });
        }
        buffer.set(chunk.value, size);
        size += chunk.value.length;
      }
    }
    body = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(buffer.subarray(0, size)));
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "Invalid login request" }, { status: 400 });
  }
  const input = body as Record<string, unknown>;
  const username = typeof input.username === "string" ? input.username : "";
  const password = typeof input.password === "string" ? input.password : "";

  const result = await authenticateAccount(username, password);
  if (!result.ok) {
    const error = {
      401: "Invalid username or password",
      429: "Too many login attempts. Try again later.",
      503: "Authentication service unavailable",
    }[result.status];
    return NextResponse.json({ error }, { status: result.status });
  }

  attempts.delete(key);
  const { token, session } = result;
  const secure = secureAuthCookies(origin);
  const maxAge = session.exp - Math.floor(Date.now() / 1000);
  const response = NextResponse.json({ ok: true, redirectTo: dashboardDestination(session.role, safeNextPath(typeof input.next === "string" ? input.next : null)) });
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge,
  });
  response.cookies.set(CSRF_COOKIE, session.csrf, {
    httpOnly: false,
    secure,
    sameSite: "strict",
    path: "/",
    maxAge,
  });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
