"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navigationItems } from "./navigation";

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
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={[
          "fixed inset-y-0 left-0 z-50 flex w-72 flex-col",
          "border-r border-zinc-800 bg-zinc-950",
          "transition-transform duration-200",
          open ? "translate-x-0" : "-translate-x-full",
          "lg:static lg:translate-x-0",
        ].join(" ")}
      >
        <div className="flex h-20 items-center justify-between border-b border-zinc-800 px-6">
          <Link
            href="/dashboard"
            className="flex items-center gap-3"
            onClick={onClose}
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-lg font-bold">
              C
            </div>

            <div>
              <p className="text-base font-bold text-white">
                CloudForge
              </p>
              <p className="text-xs text-zinc-500">
                AI Platform
              </p>
            </div>
          </Link>

          <button
            type="button"
            className="text-zinc-500 hover:text-white lg:hidden"
            aria-label="Close navigation"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-6">
          <p className="mb-3 px-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Platform
          </p>

          <nav className="space-y-1">
            {navigationItems.map((item) => {
              const isActive =
                pathname === item.href ||
                (item.href !== "/dashboard" &&
                  pathname.startsWith(`${item.href}/`));

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onClose}
                  className={[
                    "flex items-center gap-3 rounded-lg px-3 py-3",
                    "text-sm font-medium transition-colors",
                    isActive
                      ? "bg-indigo-600/15 text-indigo-300"
                      : "text-zinc-400 hover:bg-zinc-900 hover:text-white",
                  ].join(" ")}
                >
                  <span
                    className={[
                      "flex h-7 w-7 items-center justify-center rounded-md text-base",
                      isActive
                        ? "bg-indigo-600 text-white"
                        : "bg-zinc-900 text-zinc-400",
                    ].join(" ")}
                  >
                    {item.icon}
                  </span>

                  <span>{item.label}</span>

                  {isActive && (
                    <span className="ml-auto h-2 w-2 rounded-full bg-indigo-400" />
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="border-t border-zinc-800 p-4">
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              <span className="text-xs font-medium text-emerald-400">
                Development
              </span>
            </div>

            <p className="text-xs leading-5 text-zinc-500">
              CloudForge AI platform environment
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
