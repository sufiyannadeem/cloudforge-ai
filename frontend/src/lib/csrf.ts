export function secureAuthCookies(origin: string | null): boolean {
  if (process.env.CLOUDFORGE_AUTH_COOKIE_SECURE !== "false" || !origin) return true;
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

    const expectedOrigin = new URL(
      `${request.protocol}//${hostHeader}`,
    );

    return suppliedOrigin.origin === expectedOrigin.origin;
  } catch {
    return false;
  }
}

export function matchesCSRF(expected: string | null, cookie: string | undefined, header: string | null): boolean {
  return Boolean(expected && cookie === expected && header === expected);
}
