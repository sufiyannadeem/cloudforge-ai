interface MetricCardProps {
  label: string;
  value: string;
  description: string;
  icon: string;
  accent: "indigo" | "emerald" | "amber" | "rose";
}

const accentStyles = {
  indigo: "bg-indigo-500/10 text-indigo-400",
  emerald: "bg-emerald-500/10 text-emerald-400",
  amber: "bg-amber-500/10 text-amber-400",
  rose: "bg-rose-500/10 text-rose-400",
};

export default function MetricCard({
  label,
  value,
  description,
  icon,
  accent,
}: MetricCardProps) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5">
      <div className="mb-5 flex items-start justify-between">
        <p className="text-sm text-zinc-400">{label}</p>

        <div
          className={[
            "flex h-10 w-10 items-center justify-center rounded-xl text-lg",
            accentStyles[accent],
          ].join(" ")}
        >
          {icon}
        </div>
      </div>

      <p className="text-3xl font-bold tracking-tight text-white">
        {value}
      </p>

      <p className="mt-2 text-xs text-zinc-500">
        {description}
      </p>
    </div>
  );
}
