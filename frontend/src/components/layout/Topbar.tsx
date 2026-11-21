"use client";

import ProfileMenu from "./ProfileMenu";
import { useViewerSession } from "./ViewerSession";
import ThemeSwitcher from "@/components/theme/ThemeSwitcher";

interface TopbarProps {
  onMenuClick: () => void;
}

export default function Topbar({
  onMenuClick,
}: TopbarProps) {
  const viewer = useViewerSession();

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
        {viewer && <ProfileMenu viewer={viewer} />}
      </div>
    </header>
  );
}
