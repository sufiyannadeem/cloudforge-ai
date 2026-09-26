"use client";

import { useRouter } from "next/navigation";

export default function BackButton() {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => {
        if (window.history.length > 1) {
          router.back();
        } else {
          router.push("/dashboard");
        }
      }}
      className="
        inline-flex items-center gap-2
        rounded-lg
        border border-[var(--cf-border)]
        bg-[var(--cf-surface)]
        px-3 py-2
        text-sm font-medium
        text-[var(--cf-text-secondary)]
        shadow-sm
        transition-all
        hover:bg-[var(--cf-surface-2)]
        hover:text-[var(--cf-text)]
        hover:border-[var(--cf-border-strong)]
        focus:outline-none
        focus:ring-2
        focus:ring-indigo-500/30
      "
    >
      <span className="text-base leading-none" aria-hidden="true">
        ←
      </span>
      Back
    </button>
  );
}
