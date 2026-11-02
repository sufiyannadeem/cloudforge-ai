"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { InfrastructureResource } from "@/types/infrastructure";

interface ApplyApprovalModalProps {
  resource: InfrastructureResource;
  confirming: boolean;
  replanning: boolean;
  onConfirm: () => void;
  onReplan: () => void;
  onClose: () => void;
}

const RESOURCE_LABELS: Record<string, string> = {
  aws_vpc: "AWS Virtual Private Cloud (VPC)",
  aws_ec2: "AWS Elastic Compute Cloud (EC2)",
  aws_s3: "AWS Simple Storage Service (S3)",
  aws_rds: "AWS Relational Database Service (RDS)",
  aws_eks: "AWS Elastic Kubernetes Service (EKS)",
  aws_lb: "AWS Application Load Balancer (ALB)",
};

const ESTIMATED_MONTHLY_COST: Record<string, string> = {
  aws_vpc: "$0.00 / mo",
  aws_ec2: "$10.40 / mo (t3.micro)",
  aws_s3: "$5.00 / mo (standard tier)",
  aws_rds: "$18.50 / mo (db.t4g.micro + 20GB)",
  aws_eks: "$73.00 / mo (cluster) + compute",
  aws_lb: "$22.50 / mo (ALB base rate)",
};

function formatRemaining(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Human approval gate for `terraform apply cloudforge.tfplan`.
 * Infrastructure apply is NEVER executed automatically. The user must review
 * the generated plan summary, estimated cost, and plan hash, and explicitly confirm
 * before Terraform modifies AWS infrastructure.
 */
export default function ApplyApprovalModal({
  resource,
  confirming,
  replanning,
  onConfirm,
  onReplan,
  onClose,
}: ApplyApprovalModalProps) {
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

  const resourceTitle = RESOURCE_LABELS[resource.resource_type] ?? resource.resource_type;
  const estimatedCost = ESTIMATED_MONTHLY_COST[resource.resource_type] ?? "~$15.00 / mo";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="apply-approval-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
    >
      <div className="w-full max-w-2xl rounded-2xl border border-emerald-500/30 bg-[var(--cf-surface)] p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
              <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                Terraform Plan Review &amp; Approval
              </span>
            </div>
            <h2
              id="apply-approval-title"
              className="mt-1 text-xl font-bold text-[var(--cf-text)]"
            >
              Approve Provisioning: {resource.name}
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-lg p-1 text-[var(--cf-text-muted)] hover:bg-[var(--cf-surface-2)] hover:text-[var(--cf-text)] disabled:opacity-50"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Security Notice */}
        <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-700 dark:text-amber-300">
          <p className="font-semibold">⚠️ Explicit Human Approval Gate</p>
          <p className="mt-1">
            This operation will provision real AWS infrastructure via Terraform. Review the plan summary,
            configuration, and estimated cost below before confirming.
          </p>
        </div>

        {/* Metadata Details */}
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)]/50 p-3">
            <dt className="text-xs font-medium text-[var(--cf-text-muted)]">Resource &amp; Scope</dt>
            <dd className="mt-0.5 text-sm font-semibold text-[var(--cf-text)]">
              {resourceTitle}
            </dd>
            <dd className="mt-0.5 text-xs text-[var(--cf-text-secondary)]">
              {resource.environment.toUpperCase()} · {resource.region} · {resource.provider.toUpperCase()}
            </dd>
          </div>

          <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)]/50 p-3">
            <div className="flex items-center justify-between">
              <dt className="text-xs font-medium text-[var(--cf-text-muted)]">Approval Safety Window</dt>
              <span
                data-testid="apply-countdown"
                className={`font-mono text-sm font-bold ${
                  expired
                    ? "text-red-600 dark:text-red-400"
                    : remainingMs < 300_000
                      ? "text-amber-600 dark:text-amber-400"
                      : "text-emerald-600 dark:text-emerald-400"
                }`}
              >
                {expired ? "Expired" : `${formatRemaining(remainingMs)} remaining`}
              </span>
            </div>
            <dd className="mt-1 text-xs text-[var(--cf-text-secondary)]">
              {expired
                ? "Approval TTL expired. Generate a new plan to continue."
                : "30-minute lock ensures infrastructure has not drifted."}
            </dd>
          </div>
        </div>

        {/* Plan Summary Section */}
        <div className="mt-4 rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface-2)]/30 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--cf-text-secondary)]">
              Plan Actions &amp; Changes
            </h3>
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
              + 1 to add, 0 to change, 0 to destroy
            </span>
          </div>

          {resource.plan_summary ? (
            <pre className="mt-2.5 max-h-40 overflow-y-auto rounded-lg border border-[var(--cf-border)] bg-black/80 p-3 font-mono text-xs text-emerald-400 dark:text-emerald-300">
              {resource.plan_summary}
            </pre>
          ) : (
            <div className="mt-2.5 space-y-1.5 rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface)] p-3 text-xs text-[var(--cf-text-secondary)]">
              <p className="font-mono text-[var(--cf-text)]">
                + resource &quot;{resource.resource_type}&quot; &quot;{resource.name}&quot;
              </p>
              <div className="pl-3 font-mono text-[11px] text-[var(--cf-text-muted)]">
                {Object.entries(resource.configuration).slice(0, 5).map(([key, value]) => (
                  <p key={key}>
                    + {key} = {JSON.stringify(value)}
                  </p>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Cost & Verification Section */}
        <div className="mt-4 flex flex-col gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3.5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <span className="text-xs text-[var(--cf-text-secondary)]">Estimated Monthly Cost:</span>
            <p className="text-base font-bold text-emerald-700 dark:text-emerald-300">
              {estimatedCost}
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/finops"
              className="text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
            >
              Verify Cost in FinOps →
            </Link>
          </div>
        </div>

        {/* Plan Hash Verification */}
        <div className="mt-4 rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)]/40 p-2.5">
          <dt className="text-[11px] font-medium text-[var(--cf-text-muted)]">Plan SHA-256 Checksum</dt>
          <dd
            data-testid="apply-plan-hash"
            className="mt-0.5 break-all font-mono text-xs text-[var(--cf-text-secondary)]"
          >
            {resource.plan_hash ?? "—"}
          </dd>
        </div>

        {/* Action Buttons */}
        <div className="mt-6 flex flex-wrap items-center justify-end gap-3 border-t border-[var(--cf-border)] pt-4">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
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
              {replanning ? "Generating Plan..." : "Generate Fresh Plan"}
            </button>
          ) : (
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy || !resource.plan_hash}
              className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {confirming ? "Applying on AWS (Terraform)..." : "Confirm & Apply on AWS"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
