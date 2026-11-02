import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "cf_session";
export const CSRF_COOKIE = "cf_csrf";
export const SESSION_TTL_SECONDS = 8 * 60 * 60;

export type CloudForgeRole =
  | "viewer"
  | "devops"
  | "sre"
  | "platform-engineer"
  | "admin";

export interface CloudForgeSession {
  sub: string;
  role: CloudForgeRole;
  csrf: string;
  iat: number;
  exp: number;
}

export interface AuthConfig {
  username: string;
  password: string;
  secret: string;
  role: CloudForgeRole;
  cookieSecure: boolean;
}

const VALID_ROLES = new Set<CloudForgeRole>([
  "viewer",
  "devops",
  "sre",
  "platform-engineer",
  "admin",
]);

export function getAuthConfig(): AuthConfig | null {
  const username = process.env.CLOUDFORGE_AUTH_USERNAME?.trim() ?? "";
  const password = process.env.CLOUDFORGE_AUTH_PASSWORD ?? "";
  const secret = process.env.CLOUDFORGE_SESSION_SECRET ?? "";
  const configuredRole = (process.env.CLOUDFORGE_AUTH_ROLE ?? "viewer")
    .trim()
    .toLowerCase() as CloudForgeRole;

  if (
    !username ||
    !password ||
    Buffer.byteLength(secret, "utf8") < 32 ||
    secret.toLowerCase().includes("replace-with") ||
    password.toLowerCase().includes("replace-with") ||
    !VALID_ROLES.has(configuredRole)
  ) {
    return null;
  }

  return {
    username,
    password,
    secret,
    role: configuredRole,
    cookieSecure: process.env.CLOUDFORGE_AUTH_COOKIE_SECURE !== "false",
  };
}

function sign(value: string, secret: string): string {
  return createHmac("sha256", secret).update(value).digest("base64url");
}

function constantTimeEqual(left: string, right: string): boolean {
  const leftDigest = createHmac("sha256", "cloudforge-compare-v1")
    .update(left)
    .digest();
  const rightDigest = createHmac("sha256", "cloudforge-compare-v1")
    .update(right)
    .digest();
  return timingSafeEqual(leftDigest, rightDigest) && left.length === right.length;
}

export function credentialsMatch(
  username: string,
  password: string,
  config: AuthConfig,
): boolean {
  return (
    constantTimeEqual(username, config.username) &&
    constantTimeEqual(password, config.password)
  );
}

export function createSessionToken(
  username: string,
  role: CloudForgeRole,
  secret: string,
): { token: string; session: CloudForgeSession } {
  const now = Math.floor(Date.now() / 1000);
  const session: CloudForgeSession = {
    sub: username,
    role,
    csrf: randomBytes(32).toString("base64url"),
    iat: now,
    exp: now + SESSION_TTL_SECONDS,
  };
  const payload = Buffer.from(JSON.stringify(session)).toString("base64url");
  return { token: `${payload}.${sign(payload, secret)}`, session };
}

export function verifySessionToken(
  token: string | undefined,
  secret = process.env.CLOUDFORGE_SESSION_SECRET ?? "",
): CloudForgeSession | null {
  if (!token || Buffer.byteLength(secret, "utf8") < 32) return null;

  const separator = token.lastIndexOf(".");
  if (separator <= 0) return null;

  const payload = token.slice(0, separator);
  const suppliedSignature = token.slice(separator + 1);
  const expectedSignature = sign(payload, secret);
  if (!constantTimeEqual(suppliedSignature, expectedSignature)) return null;

  try {
    const session = JSON.parse(
      Buffer.from(payload, "base64url").toString("utf8"),
    ) as Partial<CloudForgeSession>;
    const now = Math.floor(Date.now() / 1000);
    if (
      typeof session.sub !== "string" ||
      !session.sub ||
      typeof session.role !== "string" ||
      !VALID_ROLES.has(session.role as CloudForgeRole) ||
      typeof session.csrf !== "string" ||
      session.csrf.length < 32 ||
      typeof session.exp !== "number" ||
      session.exp <= now ||
      typeof session.iat !== "number" ||
      session.iat > now + 60
    ) {
      return null;
    }
    return session as CloudForgeSession;
  } catch {
    return null;
  }
}

export function safeNextPath(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/dashboard";
  }
  return value;
}

export function originMatchesRequest(
  origin: string | null,
  requestUrl: string,
  hostHeader?: string | null,
): boolean {
  if (!origin || !hostHeader) return false;

  try {
    const suppliedOrigin = new URL(origin);
    const request = new URL(requestUrl);

    if (
      suppliedOrigin.username ||
      suppliedOrigin.password ||
      suppliedOrigin.pathname !== "/" ||
      suppliedOrigin.search ||
      suppliedOrigin.hash
    ) {
      return false;
    }

    const expectedOrigin = new URL(
      `${request.protocol}//${hostHeader}`,
    );

    return suppliedOrigin.origin === expectedOrigin.origin;
  } catch {
    return false;
  }
}

export function internalApiToken(): string | null {
  const token = process.env.CLOUDFORGE_INTERNAL_API_TOKEN ?? "";
  return Buffer.byteLength(token, "utf8") >= 32 && !token.toLowerCase().includes("replace-with")
    ? token
    : null;
}
