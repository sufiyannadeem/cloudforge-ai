import Link from "next/link";
import AppShell from "@/components/layout/AppShell";

export default function AccessDeniedPage() {
  return (
    <AppShell>
      <section className="mx-auto max-w-xl space-y-4 p-6 sm:p-10">
        <h1 className="text-2xl font-semibold">Access denied</h1>
        <p className="text-[var(--cf-text-secondary)]">Your role does not have access to this page.</p>
        <Link href="/dashboard" className="font-semibold text-indigo-600 dark:text-indigo-300">Return to dashboard</Link>
      </section>
    </AppShell>
  );
}
