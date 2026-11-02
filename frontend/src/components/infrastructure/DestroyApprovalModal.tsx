"use client";

import { useEffect, useState } from "react";

import type { InfrastructureResource } from "@/types/infrastructure";

interface DestroyApprovalModalProps {
  resource: InfrastructureResource;
  confirming: boolean;
  replanning: boolean;
  onConfirm: () => void;
  onReplan: () => void;
  onClose: () => void;
}

function formatRemaining(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Human approval gate for `terraform apply destroy.tfplan`.
 * The destroy only runs when the person confirms here, and the backend
 * re-verifies the plan hash and the 30 minute approval window.
 */
export default function DestroyApprovalModal({
  resource,
  confirming,
  replanning,
  onConfirm,
  onReplan,
  onClose,
}: DestroyApprovalModalProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);

    return () => window.clearInterval(timer);
  }, []);

  const expiresAt = resource.approval_expires_at
    ? new Date(resource.approval_expires_at).getTime()
    : Number.NaN;
  const remainingMs = Number.isNaN(expiresAt) ? 0 : expiresAt - now;
  const expired = remainingMs <= 0;
  const busy = confirming || replanning;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="destroy-approval-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-xl rounded-2xl border border-rose-500/30 bg-[var(--cf-surface)] p-6 shadow-xl">
        <h2
          id="destroy-approval-title"
          className="text-xl font-semibold text-rose-600 dark:text-rose-300"
        >
          Approve destroy: {resource.name}
        </h2>

        <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-sm font-medium text-rose-700 dark:text-rose-300">
          This will permanently destroy the provisioned AWS infrastructure.
        </div>

        <dl className="mt-4 space-y-3 text-sm text-[var(--cf-text-secondary)]">
          <div>
            <dt className="font-medium text-[var(--cf-text)]">Resource</dt>
            <dd>
              {resource.resource_type} · {resource.region} ·{" "}
              {resource.environment}
            </dd>
          </div>

          <div>
            <dt className="font-medium text-[var(--cf-text)]">
              Destroy plan SHA-256
            </dt>
            <dd
              data-testid="destroy-plan-hash"
              className="break-all font-mono text-xs"
            >
              {resource.destroy_plan_hash ?? "—"}
            </dd>
          </div>

          <div>
            <dt className="font-medium text-[var(--cf-text)]">
              Approval expires in
            </dt>
            <dd
              data-testid="destroy-countdown"
              className={`font-mono text-base font-semibold ${
                expired
                  ? "text-red-600 dark:text-red-300"
                  : "text-amber-600 dark:text-amber-300"
              }`}
            >
              {expired ? "Expired" : formatRemaining(remainingMs)}
            </dd>
          </div>
        </dl>

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={confirming}
            className="rounded-lg border border-[var(--cf-border)] px-4 py-2 text-sm font-medium text-[var(--cf-text-secondary)] transition hover:bg-[var(--cf-surface-2)] disabled:opacity-50"
          >
            Cancel
          </button>

          {expired ? (
            <button
              type="button"
              onClick={onReplan}
              disabled={busy}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:opacity-50"
            >
              {replanning ? "Planning..." : "Generate New Destroy Plan"}
            </button>
          ) : (
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy || !resource.destroy_plan_hash}
              className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {confirming ? "Destroying on AWS..." : "Confirm & Destroy on AWS"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
