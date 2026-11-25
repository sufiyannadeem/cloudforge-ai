// Trust only the deployment-configured public origin, never forwarded headers.
export function publicOrigin(requestUrl: string): string {
  const configured = process.env.CLOUDFORGE_PUBLIC_ORIGIN;

  if (!configured) {
    if (process.env.NODE_ENV === "production") {
      throw new Error("Public origin is required");
    }
    return new URL(requestUrl).origin;
  }

  const url = new URL(configured);

  const isLocalHTTP =
    process.env.NODE_ENV !== "production" &&
    process.env.CLOUDFORGE_LOCAL_DEV === "true" &&
    url.protocol === "http:" &&
    ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);

  if (
    (url.protocol !== "https:" && !isLocalHTTP) ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("Invalid public origin");
  }

  return url.origin;
}

export function secureAuthCookies(origin: string | null): boolean {
  if (process.env.NODE_ENV === "production" || process.env.CLOUDFORGE_AUTH_COOKIE_SECURE !== "false" || !origin) return true;
  const url = new URL(origin);
  return url.protocol !== "http:" || !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
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

    const expectedOrigin = process.env.CLOUDFORGE_PUBLIC_ORIGIN || process.env.NODE_ENV === "production"
      ? new URL(publicOrigin(requestUrl))
      : new URL(`${request.protocol}//${hostHeader}`);

    return suppliedOrigin.origin === expectedOrigin.origin;
  } catch {
    return false;
  }
}

export function matchesCSRF(expected: string | null, cookie: string | undefined, header: string | null): boolean {
  return Boolean(expected && cookie === expected && header === expected);
}
