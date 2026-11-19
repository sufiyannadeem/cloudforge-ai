import { createHash, createHmac, randomBytes } from "node:crypto";

const audiences = ["project", "infrastructure", "deployment", "aiops", "finops"] as const;
export type Audience = (typeof audiences)[number];

export function serviceAssertion(audience: Audience, url: URL, method: string,
  user?: { sub: string; role: string; exp: number }, body?: ArrayBuffer): string {
  const keys = Object.fromEntries(audiences.map((name) =>
    [name, process.env[`CLOUDFORGE_FRONTEND_${name.toUpperCase()}_KEY`]]));
  const key = keys[audience];
  if (!key || Buffer.byteLength(key) < 32 || key.toLowerCase().includes("replace-with") ||
      audiences.some((name) => name !== audience && keys[name] === key)) {
    throw new Error("Service identity is not configured");
  }
  const now = Math.floor(Date.now() / 1000);
  const payload = Buffer.from(JSON.stringify({
    iss: "frontend", aud: audience, method, target: url.pathname + url.search,
    sub: user?.sub, role: user?.role, iat: now, exp: Math.min(now + 25, user?.exp ?? now + 25),
    nonce: randomBytes(16).toString("hex"),
    body: body === undefined ? undefined : createHash("sha256").update(Buffer.from(body)).digest("hex"),
  })).toString("base64url");
  return `${payload}.${createHmac("sha256", key).update(payload).digest("hex")}`;
}
