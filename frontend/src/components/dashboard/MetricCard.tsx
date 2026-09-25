interface MetricCardProps {
  label: string;
  value: string;
  description: string;
  icon: string;
  accent: "indigo" | "emerald" | "amber" | "rose";
}

const accentStyles = {
  indigo:
    "bg-indigo-500/10 text-indigo-600 ring-1 ring-indigo-500/20 dark:text-indigo-300",
  emerald:
    "bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/20 dark:text-emerald-300",
  amber:
    "bg-amber-500/10 text-amber-700 ring-1 ring-amber-500/20 dark:text-amber-300",
  rose:
    "bg-rose-500/10 text-rose-700 ring-1 ring-rose-500/20 dark:text-rose-300",
};

export default function MetricCard({
  label,
  value,
  description,
  icon,
  accent,
}: MetricCardProps) {
  return (
    <div className="rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm transition-all hover:border-[var(--cf-border-strong)] hover:shadow-md">
      <div className="mb-5 flex items-start justify-between gap-4">
        <p className="text-sm font-medium text-[var(--cf-text-secondary)]">
          {label}
        </p>

        <div
          className={[
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg",
            accentStyles[accent],
          ].join(" ")}
        >
          {icon}
        </div>
      </div>

      <p className="text-3xl font-bold tracking-tight text-[var(--cf-text)]">
        {value}
      </p>

      <p className="mt-2 text-xs leading-5 text-[var(--cf-text-muted)]">
        {description}
      </p>
    </div>
  );
}
