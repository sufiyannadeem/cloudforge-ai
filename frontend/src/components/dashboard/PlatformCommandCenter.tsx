import Link from "next/link";
import type { CloudForgeRole } from "@/lib/auth";
import { canAccessPage, dashboardCapabilities } from "@/lib/role-access";

interface CommandCard {
  eyebrow: string;
  title: string;
  description: string;
  href: string;
  icon: string;
  accentClass: string;
}

const commandCards: CommandCard[] = ([
  ["Delivery", "Deployments", "Inspect deployment state, execution history, and delivery activity.", "/deployments", "⇧", "bg-amber-950/60 text-amber-400"],
  ["Telemetry", "Observability", "Review live service availability, traffic, errors, latency, and in-flight work.", "/observability", "◉", "bg-emerald-950/60 text-emerald-400"],
  ["Reliability", "SLO & Error Budget", "Track reliability objectives, remaining error budget, and multi-window burn rates.", "/slo", "◒", "bg-indigo-950/60 text-indigo-400"],
  ["Incident response", "AI-Ops Incidents", "Investigate incidents, review AI-assisted analysis, and manage controlled remediation.", "/incidents", "⚡", "bg-rose-950/60 text-rose-400"],
  ["AIOps", "Anomaly Detection", "Review service behavior and anomaly classifications derived from operational telemetry.", "/anomalies", "◌", "bg-violet-950/60 text-violet-400"],
  ["Infrastructure", "Infrastructure", "Inspect infrastructure resources managed through the CloudForge platform.", "/infrastructure", "⌘", "bg-cyan-950/60 text-cyan-400"],
  ["Cost Intelligence", "FinOps & Cloud Cost", "Monitor AWS cloud spend, forecast costs, and review workload right-sizing recommendations.", "/finops", "❖", "bg-teal-950/60 text-teal-400"],
] as [string, string, string, string, string, string][]).map(
  ([eyebrow, title, description, href, icon, accentClass]) => ({ eyebrow, title, description, href, icon, accentClass }),
);

const developerCards: CommandCard[] = [
  { eyebrow: "Projects", title: "My Projects", description: "Create and manage projects you can access.", href: "/projects", icon: "◈", accentClass: "bg-indigo-950/60 text-indigo-400" },
  { eyebrow: "Infrastructure", title: "Infrastructure requests", description: "Generate Terraform plans and track approval and provisioning.", href: "/infrastructure", icon: "⌘", accentClass: "bg-cyan-950/60 text-cyan-400" },
  { eyebrow: "Delivery", title: "My Deployments", description: "Deploy applications and review project deployment attempts.", href: "/deployments", icon: "⇧", accentClass: "bg-amber-950/60 text-amber-400" },
  { eyebrow: "Telemetry", title: "Project monitoring", description: "View deployment status summaries for authorized projects.", href: "/observability", icon: "◉", accentClass: "bg-emerald-950/60 text-emerald-400" },
  { eyebrow: "Costs", title: "Project FinOps", description: "Check availability of verified, read-only project costs.", href: "/project-costs", icon: "$", accentClass: "bg-teal-950/60 text-teal-400" },
];

const administrativeCards: CommandCard[] = [
  { eyebrow: "Approvals", title: "Terraform review queue", description: "Review submitted plans and execute independently approved changes.", href: "/infrastructure?review=pending", icon: "✓", accentClass: "bg-amber-950/60 text-amber-400" },
  { eyebrow: "Projects", title: "All Projects", description: "View project ownership and manage project records.", href: "/projects", icon: "◈", accentClass: "bg-indigo-950/60 text-indigo-400" },
  { eyebrow: "Administration", title: "Users & audit history", description: "Find account management and Terraform review history.", href: "/administration", icon: "◇", accentClass: "bg-violet-950/60 text-violet-400" },
];

export default function PlatformCommandCenter({ role }: { role: CloudForgeRole }) {
  const cards = role === "developer" ? developerCards :
    [...(dashboardCapabilities(role).administration ? administrativeCards : []), ...commandCards];
  return (
    <section>
      <div className="mb-4 flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
        <div>
          <h3 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
            {role === "developer" ? "Project tools" : "Operational tools"}
          </h3>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {cards.filter((card) => canAccessPage(role, card.href.split("?", 1)[0])).map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className={[
              "group rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5",
              "transition-all duration-200",
              "hover:border-[var(--cf-border-strong)] hover:bg-[var(--cf-surface)]",
              "focus:outline-none focus:ring-2 focus:ring-indigo-500/60",
            ].join(" ")}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-[var(--cf-text-muted)]">
                  {card.eyebrow}
                </p>

                <h4 className="mt-2 text-base font-semibold text-[var(--cf-text)]">
                  {card.title}
                </h4>
              </div>

              <span
                className={[
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg",
                  card.accentClass,
                ].join(" ")}
              >
                {card.icon}
              </span>
            </div>

            <p className="mt-4 text-sm leading-6 text-[var(--cf-text-muted)]">
              {card.description}
            </p>

            <div className="mt-5 flex items-center gap-2 text-sm font-medium text-indigo-400 transition-colors group-hover:text-indigo-300">
              Open
              <span
                aria-hidden="true"
                className="transition-transform group-hover:translate-x-1"
              >
                →
              </span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
