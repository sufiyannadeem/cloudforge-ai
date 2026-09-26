import Link from "next/link";

interface CommandCard {
  eyebrow: string;
  title: string;
  description: string;
  href: string;
  icon: string;
  accentClass: string;
}

const commandCards: CommandCard[] = [
  {
    eyebrow: "Delivery",
    title: "Deployments",
    description:
      "Inspect deployment state, execution history, and delivery activity.",
    href: "/deployments",
    icon: "⇧",
    accentClass: "bg-amber-950/60 text-amber-400",
  },
  {
    eyebrow: "Telemetry",
    title: "Observability",
    description:
      "Review live service availability, traffic, errors, latency, and in-flight work.",
    href: "/observability",
    icon: "◉",
    accentClass: "bg-emerald-950/60 text-emerald-400",
  },
  {
    eyebrow: "Reliability",
    title: "SLO & Error Budget",
    description:
      "Track reliability objectives, remaining error budget, and multi-window burn rates.",
    href: "/slo",
    icon: "◒",
    accentClass: "bg-indigo-950/60 text-indigo-400",
  },
  {
    eyebrow: "Incident response",
    title: "AI-Ops Incidents",
    description:
      "Investigate incidents, review AI-assisted analysis, and manage controlled remediation.",
    href: "/incidents",
    icon: "⚡",
    accentClass: "bg-rose-950/60 text-rose-400",
  },
  {
    eyebrow: "AIOps",
    title: "Anomaly Detection",
    description:
      "Review service behavior and anomaly classifications derived from operational telemetry.",
    href: "/anomalies",
    icon: "◌",
    accentClass: "bg-violet-950/60 text-violet-400",
  },
  {
    eyebrow: "Infrastructure",
    title: "Infrastructure",
    description:
      "Inspect infrastructure resources managed through the CloudForge platform.",
    href: "/infrastructure",
    icon: "⌘",
    accentClass: "bg-cyan-950/60 text-cyan-400",
  },
];

export default function PlatformCommandCenter() {
  return (
    <section>
      <div className="mb-4 flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-medium text-indigo-400">
            Platform control plane
          </p>

          <h3 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
            Command center
          </h3>

          <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--cf-text-muted)]">
            Move from platform health to delivery, reliability,
            observability, and AI-assisted incident response without
            leaving the CloudForge control plane.
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {commandCards.map((card) => (
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
