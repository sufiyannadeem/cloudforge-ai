interface ServiceHealthCardProps {
  name: string;
  description: string;
  port: number;
  status: "healthy" | "unhealthy" | "not-checked";
  latencyMs?: number | null;
  error?: string;
}

const statusStyles = {
  healthy: "bg-emerald-500/10 text-emerald-400",
  unhealthy: "bg-rose-500/10 text-rose-400",
  "not-checked": "bg-zinc-800 text-zinc-400",
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
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-zinc-800 text-sm">
            ◉
          </div>

          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">
              {name}
            </p>

            <p className="mt-1 text-xs text-zinc-500">
              {description}
            </p>
          </div>
        </div>

        <span
          className={[
            "shrink-0 rounded-full px-2 py-1 text-[10px] font-semibold uppercase",
            statusStyles[status],
          ].join(" ")}
        >
          {statusLabels[status]}
        </span>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-zinc-800 pt-3">
        <span className="text-xs text-zinc-500">
          Service port
        </span>

        <span className="font-mono text-xs text-zinc-300">
          :{port}
        </span>
      </div>

      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-zinc-500">
          Response time
        </span>

        <span className="text-xs text-zinc-400">
          {latencyMs === null || latencyMs === undefined
            ? "—"
            : `${latencyMs} ms`}
        </span>
      </div>

      {error && (
        <p className="mt-3 truncate text-xs text-rose-400" title={error}>
          {error}
        </p>
      )}
    </div>
  );
}
