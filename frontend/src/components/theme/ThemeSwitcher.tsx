"use client";

import { useSyncExternalStore } from "react";

import {
  useTheme,
  type ThemeMode,
} from "./ThemeProvider";

const options: Array<{
  value: ThemeMode;
  label: string;
  icon: string;
}> = [
  {
    value: "light",
    label: "Light",
    icon: "☀",
  },
  {
    value: "dark",
    label: "Dark",
    icon: "☾",
  },
  {
    value: "system",
    label: "System",
    icon: "◐",
  },
];

function subscribe() {
  return () => {};
}

function getClientSnapshot() {
  return true;
}

function getServerSnapshot() {
  return false;
}

export default function ThemeSwitcher() {
  const {
    theme,
    resolvedTheme,
    setTheme,
  } = useTheme();

  const hydrated = useSyncExternalStore(
    subscribe,
    getClientSnapshot,
    getServerSnapshot,
  );

  if (!hydrated) {
    return (
      <div
        aria-hidden="true"
        className={[
          "h-9 w-24 rounded-lg border",
          "border-[var(--cf-border)]",
          "bg-[var(--cf-surface-2)]",
        ].join(" ")}
      />
    );
  }

  const current =
    options.find(
      (option) => option.value === theme,
    ) ?? options[2];

  return (
    <div className="relative">
      <button
        type="button"
        aria-label="Change appearance"
        aria-haspopup="menu"
        className={[
          "flex h-9 items-center gap-2 rounded-lg border px-3",
          "border-[var(--cf-border)]",
          "bg-[var(--cf-surface-2)]",
          "text-sm text-[var(--cf-text-secondary)]",
          "transition-colors",
          "hover:bg-[var(--cf-surface-3)]",
          "hover:text-[var(--cf-text)]",
        ].join(" ")}
        onClick={() => {
          const menu =
            document.getElementById(
              "cloudforge-theme-menu",
            );

          if (menu) {
            menu.toggleAttribute("hidden");
          }
        }}
      >
        <span className="text-base">
          {current.icon}
        </span>

        <span className="hidden sm:inline">
          {current.label}
        </span>

        <span className="text-xs opacity-60">
          ▾
        </span>
      </button>

      <ThemeMenu
        theme={theme}
        resolvedTheme={resolvedTheme}
        setTheme={setTheme}
      />
    </div>
  );
}

function ThemeMenu({
  theme,
  resolvedTheme,
  setTheme,
}: {
  theme: ThemeMode;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: ThemeMode) => void;
}) {
  return (
    <div
      id="cloudforge-theme-menu"
      hidden
      className={[
        "absolute right-0 z-50 mt-2 w-44 overflow-hidden",
        "rounded-xl border shadow-xl",
        "border-[var(--cf-border)]",
        "bg-[var(--cf-surface)]",
        "p-1",
      ].join(" ")}
    >
      <div className="px-3 py-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-muted)]">
          Appearance
        </p>

        <p className="mt-1 text-xs text-[var(--cf-text-muted)]">
          Currently {resolvedTheme}
        </p>
      </div>

      {options.map((option) => {
        const active =
          option.value === theme;

        return (
          <button
            key={option.value}
            type="button"
            className={[
              "flex w-full items-center gap-3 rounded-lg px-3 py-2.5",
              "text-sm transition-colors",
              active
                ? "bg-indigo-500/10 text-indigo-500"
                : "text-[var(--cf-text-secondary)] hover:bg-[var(--cf-surface-2)] hover:text-[var(--cf-text)]",
            ].join(" ")}
            onClick={() => {
              setTheme(option.value);

              const menu =
                document.getElementById(
                  "cloudforge-theme-menu",
                );

              if (menu) {
                menu.setAttribute("hidden", "");
              }
            }}
          >
            <span className="w-5 text-center">
              {option.icon}
            </span>

            <span>{option.label}</span>

            {active && (
              <span className="ml-auto text-indigo-500">
                ✓
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
