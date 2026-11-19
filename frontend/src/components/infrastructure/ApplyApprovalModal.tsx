"use client";

import { useEffect, useState } from "react";
import RequestEstimate from "./RequestEstimate";
import type { InfrastructureResource, PlanDetails } from "@/types/infrastructure";

export type ReviewAction = "submit" | "approve" | "reject";

interface ApplyApprovalModalProps {
  resource: InfrastructureResource;
  plan: PlanDetails | null;
  operator: boolean;
  developer: boolean;
  username: string;
  busy: boolean;
  message: string;
  onDecision: (action: ReviewAction) => void;
  onConfirm: () => void;
  onReplan: () => void;
  onClose: () => void;
}

export default function ApplyApprovalModal({
  resource, plan, operator, developer, username, busy, message,
  onDecision, onConfirm, onReplan, onClose,
}: ApplyApprovalModalProps) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  const destroy = plan?.operation === "destroy";
  const review = plan?.reviews?.find((item) => item.operation === plan.operation && item.revision === plan.revision);
  const awaiting = plan?.status === "awaiting_approval" || plan?.status === "awaiting_destroy_approval";
  const expired = !plan?.approval_expires_at || Date.parse(plan.approval_expires_at) <= now;
  const canSubmit = operator || (developer && !destroy);
  const eligible = awaiting && !expired && Boolean(plan?.requester && plan?.plan_hash && plan?.project_id);
  const mayDecide = operator && username !== plan?.requester && username !== review?.submitted_by && review?.status === "submitted";
  const button = "rounded-lg border border-[var(--cf-border)] px-3 py-2 text-sm font-medium disabled:opacity-50";
  const primary = `${button} ${destroy ? "bg-rose-600" : "bg-indigo-600"} text-white`;
  const formatDate = (value: string) => new Date(value).toLocaleString();

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="plan-review-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl space-y-4 overflow-y-auto rounded-2xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <h2 id="plan-review-title" className="text-xl font-semibold">{destroy ? "Destroy plan" : "Terraform plan"} · {resource.name}</h2>
          <button className={button} type="button" onClick={onClose} disabled={busy}>Close</button>
        </div>
        {message && <p role="status" className="rounded border border-[var(--cf-border)] p-2 text-sm">{message}</p>}
        {!plan && !message && <p>Loading saved plan…</p>}
        {plan && <>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div><dt className="font-semibold">Requester</dt><dd>{plan.requester ?? "Unverified legacy requester"}</dd></div>
            <div><dt className="font-semibold">Project</dt><dd className="break-all">{plan.project_id ?? "Unassigned"}</dd></div>
            <div><dt className="font-semibold">Environment</dt><dd>{plan.environment} · {plan.region}</dd></div>
            <div><dt className="font-semibold">Review</dt><dd>{review?.status ?? (awaiting ? "Draft" : plan.status)}{awaiting && expired ? " · Expired" : ""}</dd></div>
          </dl>
          <section className="rounded-lg border border-[var(--cf-border)] p-3 text-sm">
            <h3 className="font-semibold">Saved plan</h3>
            <pre className="whitespace-pre-wrap">{plan.plan_summary || "Change counts unavailable."}</pre>
            <p className="mt-2">{destroy ? "Applying this plan removes AWS resources." : "Applying this plan changes AWS infrastructure."}</p>
            <RequestEstimate key={plan.revision} plan={plan} />
            {plan.plan_hash && <p className="mt-2 break-all font-mono text-xs">SHA-256 {plan.plan_hash}</p>}
          </section>
          {plan.reviews && plan.reviews.length > 0 && <section>
            <h3 className="font-semibold">Review history</h3>
            <ul className="mt-2 space-y-2 text-sm">
              {plan.reviews.map((entry) => <li key={`${entry.operation}-${entry.revision}`} className="rounded border border-[var(--cf-border)] p-2">
                <p className="font-medium">{entry.operation} · {entry.status}</p>
                <p>Submitted by {entry.submitted_by} · {formatDate(entry.submitted_at)}</p>
                {entry.decided_by && entry.decided_at && <p>Decision by {entry.decided_by} · {formatDate(entry.decided_at)}</p>}
                {entry.executed_by && entry.execution_started_at && <p>Executed by {entry.executed_by} · {formatDate(entry.execution_started_at)}</p>}
              </li>)}
            </ul>
          </section>}
          {eligible && operator && review?.status === "submitted" && !mayDecide && (
            <p className="text-sm">A different Platform Engineer must approve this request.</p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            {awaiting && expired && canSubmit && <button type="button" className={button} disabled={busy} onClick={onReplan}>Generate new plan</button>}
            {eligible && !review && canSubmit && <button type="button" className={primary} disabled={busy} onClick={() => onDecision("submit")}>Submit for approval</button>}
            {eligible && mayDecide && <>
              <button type="button" className={button} disabled={busy} onClick={() => onDecision("reject")}>Reject plan</button>
              <button type="button" className={primary} disabled={busy} onClick={() => onDecision("approve")}>Approve saved plan</button>
            </>}
            {eligible && operator && review?.status === "approved" && <button type="button" className={primary} disabled={busy} onClick={onConfirm}>
              {busy ? "Executing…" : destroy ? "Execute approved destroy" : "Execute approved apply"}
            </button>}
          </div>
        </>}
      </div>
    </div>
  );
}
