import { createHmac } from "node:crypto";
import { serviceAssertion } from "@/lib/service-identity";
import { serviceConfig } from "@/lib/server-config";

export const SESSION_COOKIE = "cf_session";
export const CSRF_COOKIE = "cf_csrf";

export const PLATFORM_ROLES = ["platform-engineer", "sre", "developer"] as const;
export type CloudForgeRole = (typeof PLATFORM_ROLES)[number];

export interface CloudForgeSession {
  sub: string;
  email: string | null;
  role: CloudForgeRole;
  csrf: string;
  exp: number;
}

interface AccountIdentity {
  username: string;
  email?: string | null;
  role: CloudForgeRole;
  expiresAt: number;
}

function csrfSecret(): string | null {
  const secret = process.env.CLOUDFORGE_SESSION_SECRET ?? "";
  return Buffer.byteLength(secret) >= 32 && !secret.toLowerCase().includes("replace-with") ? secret : null;
}

function sessionFromIdentity(identity: AccountIdentity, csrf: string): CloudForgeSession | null {
  if (typeof identity.username !== "string" || !identity.username || !PLATFORM_ROLES.includes(identity.role) ||
      !Number.isSafeInteger(identity.expiresAt) || identity.expiresAt <= Math.floor(Date.now() / 1000)) {
    return null;
  }
  return {
    sub: identity.username,
    email: typeof identity.email === "string" ? identity.email : null,
    role: identity.role,
    exp: identity.expiresAt,
    csrf,
  };
}

function validToken(token: unknown): token is string {
  return typeof token === "string" && /^[A-Za-z0-9_-]{43}$/.test(token);
}

export function sessionCSRF(token: string | undefined): string | null {
  const secret = csrfSecret();
  return validToken(token) && secret
    ? createHmac("sha256", secret).update("csrf-v2:").update(token).digest("base64url")
    : null;
}

async function accountRequest(operation: "login" | "session" | "logout", token?: string, body?: string) {
  const url = new URL(`${serviceConfig.project.replace(/\/$/, "")}/internal/auth/${operation}`);
  const headers = new Headers({ "X-CloudForge-Identity": serviceAssertion("project", url, "POST") });
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (body) headers.set("Content-Type", "application/json");

  return fetch(url, {
    method: "POST",
    headers,
    body,
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(5000),
  });
}

type LoginResult =
  | { ok: true; token: string; session: CloudForgeSession }
  | { ok: false; status: 401 | 429 | 503 };

export async function authenticateAccount(username: string, password: string): Promise<LoginResult> {
  if (!csrfSecret()) return { ok: false, status: 503 };
  try {
    const response = await accountRequest("login", undefined, JSON.stringify({ username, password }));
    if (response.status === 401 || response.status === 429) return { ok: false, status: response.status };
    if (!response.ok) return { ok: false, status: 503 };
    const login = await response.json() as AccountIdentity & { token: string };
    const csrf = sessionCSRF(login.token);
    const session = csrf && sessionFromIdentity(login, csrf);
    return session ? { ok: true, token: login.token, session } : { ok: false, status: 503 };
  } catch {
    return { ok: false, status: 503 };
  }
}

export async function verifySessionToken(token: string | undefined): Promise<CloudForgeSession | null> {
  const csrf = sessionCSRF(token);
  if (!csrf) return null;
  try {
    const response = await accountRequest("session", token);
    return response.ok ? sessionFromIdentity(await response.json() as AccountIdentity, csrf) : null;
  } catch {
    return null;
  }
}

export async function revokeSession(token: string | undefined): Promise<boolean> {
  if (!validToken(token)) return false;
  try {
    return (await accountRequest("logout", token)).status === 204;
  } catch {
    return false;
  }
}

export function safeNextPath(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/dashboard";
  }
  return value;
}
