"use client";

import type { Deployment } from "@/types/deployments";

interface RollbackModalProps {
  deployment: Deployment;
  projectName: string;
  loading: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export default function RollbackModal({
  deployment,
  projectName,
  loading,
  onConfirm,
  onClose,
}: RollbackModalProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="rollback-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
    >
      <div className="w-full max-w-lg rounded-2xl border border-amber-500/30 bg-[var(--cf-surface)] p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-amber-500" />
              <span className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400">
                Safe Workload Rollback
              </span>
            </div>
            <h2
              id="rollback-modal-title"
              className="mt-1 text-xl font-bold text-[var(--cf-text)]"
            >
              Rollback {projectName}
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="rounded-lg p-1 text-[var(--cf-text-muted)] hover:bg-[var(--cf-surface-2)] hover:text-[var(--cf-text)] disabled:opacity-50"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Safety Warning */}
        <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-700 dark:text-amber-300">
          <p className="font-semibold">⚠️ Controlled Rollback Procedure</p>
          <p className="mt-1">
            This operation will query previous deployment history for{" "}
            <strong>{deployment.environment}</strong>, identify the last known-good successful
            release, and initiate a zero-downtime rolling recovery on the Kubernetes cluster.
          </p>
        </div>

        {/* Deployment details */}
        <div className="mt-4 space-y-2 rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)]/50 p-3 text-xs">
          <div className="flex justify-between">
            <span className="text-[var(--cf-text-muted)]">Target Environment:</span>
            <span className="font-semibold capitalize text-[var(--cf-text)]">
              {deployment.environment}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--cf-text-muted)]">Namespace:</span>
            <span className="font-mono text-[var(--cf-text)]">
              {deployment.namespace}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--cf-text-muted)]">Current Workload:</span>
            <span className="truncate max-w-[240px] font-mono text-[var(--cf-text)]" title={deployment.image}>
              {deployment.image}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--cf-text-muted)]">Current Commit:</span>
            <span className="font-mono text-[var(--cf-text)]">
              {deployment.git_commit_sha.slice(0, 7)}
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="mt-6 flex items-center justify-end gap-3 border-t border-[var(--cf-border)] pt-4">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="rounded-lg border border-[var(--cf-border)] px-4 py-2 text-sm font-medium text-[var(--cf-text-secondary)] transition hover:bg-[var(--cf-surface-2)] disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Rolling Back..." : "Confirm & Execute Rollback"}
          </button>
        </div>
      </div>
    </div>
  );
}
