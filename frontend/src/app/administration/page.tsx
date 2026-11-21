import AccountAdministration from "@/components/administration/AccountAdministration";
import Link from "next/link";
import { redirect } from "next/navigation";
import AppShell from "@/components/layout/AppShell";
import { requireSession } from "@/lib/server-session";

export default async function AdministrationPage() {
  const session = await requireSession();
  if (session.role !== "platform-engineer") redirect("/access-denied");

  return (
    <AppShell>
      <section className="mx-auto max-w-7xl space-y-5 p-6 sm:p-8">
        <h1 className="text-3xl font-semibold">Administration</h1>
        <div className="grid gap-4">
          <article className="space-y-3 rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5">
            <h2 className="text-lg font-semibold">User management</h2>
            <AccountAdministration />
          </article>
          <article className="space-y-3 rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5">
            <h2 className="text-lg font-semibold">Approval audit history</h2>
            <p className="text-sm text-[var(--cf-text-secondary)]">Review requesters, decisions, and execution outcomes in each infrastructure resource’s review history.</p>
            <Link href="/infrastructure" className="text-sm font-semibold text-indigo-600 dark:text-indigo-300">Open infrastructure</Link>
          </article>
        </div>
      </section>
    </AppShell>
  );
}
