"use client";

import AppShell from "@/components/layout/AppShell";

export default function DashboardError({ reset }: { reset: () => void }) {
  return <AppShell><section className="space-y-3 p-6">
    <h1 className="text-xl font-semibold">Dashboard unavailable</h1>
    <button type="button" onClick={reset} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white">Try again</button>
  </section></AppShell>;
}
