import { infrastructureFields, type InfrastructureValues } from "@/lib/infrastructure-form";

const input = "w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-[var(--cf-text)]";

export default function InfrastructureFields({ type, values, onChange }: {
  type: string;
  values: InfrastructureValues;
  onChange: (key: string, value: string | boolean) => void;
}) {
  return (
    <fieldset className="mt-5 grid gap-4 md:grid-cols-2">
      <legend className="mb-3 text-sm font-semibold">Resource configuration</legend>
      {(infrastructureFields[type] ?? []).map((field) => {
        const value = values[field.key] ?? field.value;
        return (
          <label key={field.key} className="space-y-1 text-sm">
            {typeof value === "boolean" ? (
              <span className="flex min-h-11 items-center gap-2">
                <input type="checkbox" checked={value} onChange={(event) => onChange(field.key, event.target.checked)} />
                {field.label}
              </span>
            ) : <>
              <span className="block font-medium">{field.label}</span>
              {field.options ? (
                <select className={input} value={value} onChange={(event) => onChange(field.key, event.target.value)}>
                  {field.options.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              ) : (
                <input className={input} type={field.min === undefined ? "text" : "number"}
                  required={field.required} min={field.min} max={field.max} step={field.min === undefined ? undefined : 1}
                  value={value} onChange={(event) => onChange(field.key, event.target.value)} />
              )}
            </>}
            {field.hint && <span className="block text-xs text-[var(--cf-text-muted)]">{field.hint}</span>}
          </label>
        );
      })}
    </fieldset>
  );
}
