"use client";

import { useEffect, useRef, useState } from "react";
import type { CloudForgeRole } from "@/lib/auth";

const roleLabels: Record<CloudForgeRole, string> = {
  "platform-engineer": "Platform Engineer",
  sre: "SRE",
  developer: "Developer",
};

interface ProfileViewer {
  username: string;
  email: string | null;
  role: CloudForgeRole;
  csrfToken: string;
}

export default function ProfileMenu({ viewer }: { viewer: ProfileViewer }) {
  const menu = useRef<HTMLDetailsElement>(null);
  const trigger = useRef<HTMLElement>(null);
  const [status, setStatus] = useState<"idle" | "pending" | "error">("idle");

  useEffect(() => {
    function dismiss(event: PointerEvent) {
      if (menu.current?.open && event.target instanceof Node && !menu.current.contains(event.target)) {
        menu.current.open = false;
      }
    }

    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, []);

  async function signOut() {
    setStatus("pending");
    try {
      const response = await fetch("/api/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": viewer.csrfToken },
        cache: "no-store",
      });
      if (response.ok) {
        window.location.replace("/login");
        return;
      }
    } catch {
      // Keep the current view when the server cannot confirm revocation.
    }
    setStatus("error");
  }

  return (
    <details
      ref={menu}
      className="relative z-30"
      onKeyDown={(event) => {
        if (event.key === "Escape" && menu.current?.open) {
          event.preventDefault();
          menu.current.open = false;
          trigger.current?.focus();
        }
      }}
    >
      <summary ref={trigger} aria-label="Profile" className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-lg border border-[var(--cf-border)] px-2 text-sm hover:bg-[var(--cf-surface-2)] sm:px-3 [&::-webkit-details-marker]:hidden">
        <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center rounded-full bg-[var(--cf-surface-2)] font-semibold">
          {viewer.username.charAt(0).toUpperCase()}
        </span>
        <span aria-hidden="true" className="hidden max-w-32 truncate sm:inline">{viewer.username}</span>
        <span aria-hidden="true">▾</span>
      </summary>

      <div className="absolute right-0 top-full mt-2 w-72 max-w-[calc(100vw-2rem)] rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-4 text-sm shadow-lg">
        <dl className="space-y-2 break-words">
          <div><dt className="text-xs text-[var(--cf-text-muted)]">Name</dt><dd className="font-semibold">{viewer.username}</dd></div>
          <div><dt className="text-xs text-[var(--cf-text-muted)]">Email</dt><dd>{viewer.email || "Not provided"}</dd></div>
          <div><dt className="text-xs text-[var(--cf-text-muted)]">Role</dt><dd>{roleLabels[viewer.role]}</dd></div>
        </dl>
        <button
          type="button"
          disabled={status === "pending"}
          onClick={() => void signOut()}
          className="mt-4 min-h-11 w-full rounded-lg border border-[var(--cf-border)] px-3 text-left font-medium hover:bg-[var(--cf-surface-2)] disabled:opacity-60"
        >
          {status === "pending" ? "Signing out…" : "Sign Out"}
        </button>
        {status === "error" && <p role="alert" className="mt-2 text-xs">Sign-out failed. Try again.</p>}
      </div>
    </details>
  );
}
