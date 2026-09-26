"use client";

import ThemeSwitcher from "@/components/theme/ThemeSwitcher";

interface TopbarProps {
  onMenuClick: () => void;
}

export default function Topbar({
  onMenuClick,
}: TopbarProps) {
  return (
    <header
      className={[
        "flex h-20 items-center justify-between",
        "border-b px-4 backdrop-blur",
        "border-[var(--cf-border)]",
        "bg-[var(--cf-surface)]/90",
        "sm:px-6",
      ].join(" ")}
    >
      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Open navigation"
          className={[
            "rounded-lg border px-3 py-2",
            "border-[var(--cf-border)]",
            "text-[var(--cf-text-secondary)]",
            "transition-colors",
            "hover:bg-[var(--cf-surface-2)]",
            "hover:text-[var(--cf-text)]",
            "lg:hidden",
          ].join(" ")}
          onClick={onMenuClick}
        >
          ☰
        </button>

        <div>
          <p className="text-sm font-medium text-[var(--cf-text-muted)]">
            Platform Console
          </p>

          <h1 className="text-lg font-semibold text-[var(--cf-text)]">
            CloudForge AI
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <ThemeSwitcher />

        <div
          className={[
            "hidden items-center gap-2 rounded-full border px-3 py-2",
            "border-[var(--cf-border)]",
            "bg-[var(--cf-surface-2)]",
            "sm:flex",
          ].join(" ")}
        >
          <span className="h-2 w-2 rounded-full bg-emerald-500" />

          <span className="text-xs text-[var(--cf-text-secondary)]">
            Local environment
          </span>
        </div>

        <button
          type="button"
          aria-label="User profile"
          className={[
            "flex h-9 w-9 items-center justify-center rounded-full",
            "bg-indigo-600 text-sm font-semibold text-white",
            "transition-transform hover:scale-105",
            "focus:outline-none focus:ring-2 focus:ring-indigo-500",
            "focus:ring-offset-2",
            "focus:ring-offset-[var(--cf-background)]",
          ].join(" ")}
        >
          NS
        </button>
      </div>
    </header>
  );
}
