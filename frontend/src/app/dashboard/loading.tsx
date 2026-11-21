import AppShell from "@/components/layout/AppShell";

export default function Loading() {
  return <AppShell><p role="status" className="p-6 text-sm text-[var(--cf-text-secondary)]">Loading dashboard…</p></AppShell>;
}
