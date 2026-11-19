"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import type { CloudForgeRole } from "@/lib/auth";

interface Viewer {
  username: string;
  email: string | null;
  csrfToken: string;
  role: CloudForgeRole;
  expiresAt: number;
}

const ViewerContext = createContext<Viewer | null>(null);

export function ViewerSession({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [session, setSession] = useState<{ path: string; viewer: Viewer } | null>(null);

  useEffect(() => {
    if (path === "/login") return;
    const controller = new AbortController();
    let expiry: ReturnType<typeof setTimeout> | undefined;
    const goToLogin = () => {
      const next = window.location.pathname + window.location.search;
      window.location.replace(`/login?next=${encodeURIComponent(next)}`);
    };

    fetch("/api/auth/session", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (controller.signal.aborted) return;
        if (response.status === 401) {
          goToLogin();
          return;
        }
        if (!response.ok) return;
        const viewer = await response.json() as Viewer;
        if (controller.signal.aborted) return;
        if (viewer.expiresAt * 1000 <= Date.now()) {
          goToLogin();
          return;
        }
        setSession({ path, viewer });
        expiry = setTimeout(goToLogin, viewer.expiresAt * 1000 - Date.now());
      }).catch(() => {});
    return () => {
      controller.abort();
      if (expiry) clearTimeout(expiry);
    };
  }, [path]);

  return <ViewerContext.Provider value={session?.path === path ? session.viewer : null}>{children}</ViewerContext.Provider>;
}

export function useViewerSession() {
  return useContext(ViewerContext);
}
