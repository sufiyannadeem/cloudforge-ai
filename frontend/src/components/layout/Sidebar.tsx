"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { navigationGroups } from "./navigation";

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export default function Sidebar({
  open,
  onClose,
}: SidebarProps) {
  const pathname = usePathname();

  return (
    <>
      {open && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px] lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={[
          "fixed inset-y-0 left-0 z-50 flex w-72 flex-col",
          "border-r border-[var(--cf-border)]",
          "bg-[var(--cf-surface)]",
          "transition-transform duration-200",
          open
            ? "translate-x-0"
            : "-translate-x-full",
          "lg:static lg:translate-x-0",
        ].join(" ")}
      >
        <div
          className={[
            "flex h-20 items-center justify-between px-6",
            "border-b border-[var(--cf-border)]",
          ].join(" ")}
        >
          <Link
            href="/dashboard"
            className="flex items-center gap-3"
            onClick={onClose}
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-lg font-bold text-white shadow-sm">
              C
            </div>

            <div>
              <p className="text-base font-bold text-[var(--cf-text)]">
                CloudForge
              </p>

              <p className="text-xs text-[var(--cf-text-muted)]">
                AI Platform
              </p>
            </div>
          </Link>

          <button
            type="button"
            aria-label="Close navigation"
            className="text-[var(--cf-text-muted)] hover:text-[var(--cf-text)] lg:hidden"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-6">
          <nav className="space-y-7">
            {navigationGroups.map((group) => (
              <div key={group.label}>
                <p className="mb-3 px-3 text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-muted)]">
                  {group.label}
                </p>

                <div className="space-y-1">
                  {group.items.map((item) => {
                    const isActive =
                      pathname === item.href ||
                      (item.href !== "/dashboard" &&
                        pathname.startsWith(
                          `${item.href}/`,
                        ));

                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={onClose}
                        className={[
                          "flex items-center gap-3 rounded-lg px-3 py-3",
                          "text-sm font-medium transition-colors",
                          isActive
                            ? "bg-indigo-500/10 text-indigo-600 dark:text-indigo-300"
                            : [
                                "text-[var(--cf-text-secondary)]",
                                "hover:bg-[var(--cf-surface-2)]",
                                "hover:text-[var(--cf-text)]",
                              ].join(" "),
                        ].join(" ")}
                      >
                        <span
                          className={[
                            "flex h-7 w-7 items-center justify-center rounded-md text-base",
                            isActive
                              ? "bg-indigo-600 text-white"
                              : [
                                  "bg-[var(--cf-surface-2)]",
                                  "text-[var(--cf-text-secondary)]",
                                ].join(" "),
                          ].join(" ")}
                        >
                          {item.icon}
                        </span>

                        <span>{item.label}</span>

                        {isActive && (
                          <span className="ml-auto h-2 w-2 rounded-full bg-indigo-500" />
                        )}
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>
        </div>

        <div className="border-t border-[var(--cf-border)] p-4">
          <div
            className={[
              "rounded-xl border p-4",
              "border-[var(--cf-border)]",
              "bg-[var(--cf-surface-2)]",
            ].join(" ")}
          >
            <div className="mb-2 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />

              <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">
                Development
              </span>
            </div>

            <p className="text-xs leading-5 text-[var(--cf-text-muted)]">
              CloudForge AI platform environment
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
