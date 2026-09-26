interface ServiceHealthCardProps {
  name: string;
  description: string;
  port: number;
  status: "healthy" | "unhealthy" | "not-checked";
  latencyMs?: number | null;
  error?: string;
}

const statusStyles = {
  healthy:
    "bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/20 dark:text-emerald-300",
  unhealthy:
    "bg-rose-500/10 text-rose-700 ring-1 ring-rose-500/20 dark:text-rose-300",
  "not-checked":
    "bg-slate-500/10 text-slate-700 ring-1 ring-slate-500/20 dark:text-slate-300",
};

const statusLabels = {
  healthy: "Healthy",
  unhealthy: "Unhealthy",
  "not-checked": "Not checked",
};

export default function ServiceHealthCard({
  name,
  description,
  port,
  status,
  latencyMs,
  error,
}: ServiceHealthCardProps) {
  return (
    <div className="rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-5 shadow-sm transition-all hover:border-[var(--cf-border-strong)] hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--cf-surface-2)] text-sm text-indigo-600 ring-1 ring-[var(--cf-border)] dark:text-indigo-300">
            ◉
          </div>

          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-[var(--cf-text)]">
              {name}
            </p>

            <p className="mt-1 truncate text-xs text-[var(--cf-text-muted)]">
              {description}
            </p>
          </div>
        </div>

        <span
          className={[
            "shrink-0 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide",
            statusStyles[status],
          ].join(" ")}
        >
          {statusLabels[status]}
        </span>
      </div>

      <div className="mt-5 space-y-2 border-t border-[var(--cf-border)] pt-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--cf-text-muted)]">
            Service port
          </span>

          <span className="font-mono text-xs font-medium text-[var(--cf-text-secondary)]">
            :{port}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--cf-text-muted)]">
            Response time
          </span>

          <span className="text-xs font-medium text-[var(--cf-text-secondary)]">
            {latencyMs === null || latencyMs === undefined
              ? "—"
              : `${latencyMs} ms`}
          </span>
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-rose-500/20 bg-rose-500/5 px-3 py-2">
          <p className="truncate text-xs text-rose-600 dark:text-rose-300" title={error}>
            {error}
          </p>
        </div>
      )}
    </div>
  );
}
