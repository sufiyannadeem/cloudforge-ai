"use client";

import { useState } from "react";

import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

interface AppShellProps {
  children: React.ReactNode;
}

export default function AppShell({
  children,
}: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] =
    useState(false);

  return (
    <div
      className={[
        "flex min-h-screen",
        "bg-[var(--cf-background)]",
        "text-[var(--cf-text)]",
      ].join(" ")}
    >
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          onMenuClick={() => setSidebarOpen(true)}
        />

        <main
          className={[
            "min-w-0 flex-1 overflow-x-hidden",
            "bg-[var(--cf-background)]",
          ].join(" ")}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
