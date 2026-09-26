"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  approveIncidentRemediation,
  executeIncidentRemediation,
  getIncidentRemediation,
  previewIncidentRemediation,
  rejectIncidentRemediation,
} from "@/lib/incidents-api";

import type {
  RemediationAction,
  RemediationAvailableAction,
  RemediationProposal,
  RemediationResponse,
  RemediationStatus,
} from "@/types/incidents";

const ACTOR = "nadeem";

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function actionLabel(action: RemediationAction): string {
  switch (action) {
    case "acknowledge_incident":
      return "Acknowledge incident";
    case "no_action":
      return "Record no action";
    case "rerun_deployment":
      return "Rerun deployment";
    case "restart_deployment":
      return "Restart deployment";
    case "scale_deployment":
      return "Scale deployment";
    case "rollback_deployment":
      return "Rollback deployment";
  }
}

function statusClass(status: RemediationStatus): string {
  switch (status) {
    case "PENDING_APPROVAL":
      return "border-amber-700/50 bg-amber-950/30 text-amber-300";

    case "APPROVED":
      return "border-blue-700/50 bg-blue-950/30 text-blue-300";

    case "EXECUTING":
      return "border-violet-700/50 bg-violet-950/30 text-violet-300";

    case "SUCCEEDED":
      return "border-emerald-700/50 bg-emerald-950/30 text-emerald-300";

    case "FAILED":
      return "border-rose-700/50 bg-rose-950/30 text-rose-300";

    case "REJECTED":
      return "border-[var(--cf-border)] bg-[var(--cf-surface-2)] text-[var(--cf-text-muted)]";

    case "PROPOSED":
      return "border-blue-700/50 bg-blue-950/30 text-blue-300";
  }
}

function policyClass(
  action: RemediationAvailableAction,
): string {
  if (action.policy === "blocked") {
    return "border-rose-700/50 bg-rose-950/30 text-rose-300";
  }

  if (action.human_approval_required) {
    return "border-amber-700/50 bg-amber-950/30 text-amber-300";
  }

  return "border-emerald-700/50 bg-emerald-950/30 text-emerald-300";
}

function policyLabel(
  action: RemediationAvailableAction,
): string {
  if (action.policy === "blocked") {
    return "Blocked";
  }

  if (action.human_approval_required) {
    return "Human approval required";
  }

  return "Allowed";
}

function proposalCanApprove(
  proposal: RemediationProposal,
): boolean {
  return proposal.status === "PENDING_APPROVAL";
}

function proposalCanExecute(
  proposal: RemediationProposal,
): boolean {
  return proposal.status === "APPROVED";
}

export default function RemediationPanel({
  incidentId,
}: {
  incidentId: string;
}) {
  const [data, setData] =
    useState<RemediationResponse | null>(null);

  const [selectedAction, setSelectedAction] =
    useState<RemediationAction>("acknowledge_incident");

  const [targetDeploymentId, setTargetDeploymentId] =
    useState("");

  const [reason, setReason] = useState("");

  const [rejectionReasons, setRejectionReasons] =
    useState<Record<string, string>>({});

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");

  const loadRemediation = useCallback(async () => {
    try {
      setError("");

      const result =
        await getIncidentRemediation(incidentId);

      setData(result);

      const firstExecutableAction =
        result.available_actions.find(
          (action) => action.policy !== "blocked",
        );

      if (firstExecutableAction) {
        setSelectedAction(firstExecutableAction.action);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load remediation policy.",
      );
    } finally {
      setLoading(false);
    }
  }, [incidentId]);

  useEffect(() => {
    // Load remediation policy when the incident detail mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadRemediation();
  }, [loadRemediation]);

  const selectedPolicy = useMemo(
    () =>
      data?.available_actions.find(
        (action) =>
          action.action === selectedAction,
      ) ?? null,
    [data, selectedAction],
  );

  async function handlePreview() {
    try {
      setActionLoading(true);
      setError("");

      await previewIncidentRemediation(
        incidentId,
        {
          action: selectedAction,
          target_deployment_id:
            targetDeploymentId.trim() || undefined,
          reason: reason.trim() || undefined,
          requested_by: ACTOR,
        },
      );

      setReason("");
      await loadRemediation();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to create remediation proposal.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function handleApprove(
    proposal: RemediationProposal,
  ) {
    try {
      setActionLoading(true);
      setError("");

      await approveIncidentRemediation(
        incidentId,
        proposal.id,
        ACTOR,
      );

      await loadRemediation();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to approve remediation.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function handleReject(
    proposal: RemediationProposal,
  ) {
    const rejectionReason =
      rejectionReasons[proposal.id]?.trim();

    if (!rejectionReason) {
      setError(
        "Enter a rejection reason before rejecting the proposal.",
      );
      return;
    }

    try {
      setActionLoading(true);
      setError("");

      await rejectIncidentRemediation(
        incidentId,
        proposal.id,
        ACTOR,
        rejectionReason,
      );

      setRejectionReasons((current) => {
        const next = { ...current };
        delete next[proposal.id];
        return next;
      });

      await loadRemediation();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to reject remediation.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function handleExecute(
    proposal: RemediationProposal,
  ) {
    try {
      setActionLoading(true);
      setError("");

      await executeIncidentRemediation(
        incidentId,
        proposal.id,
        ACTOR,
      );

      await loadRemediation();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to execute remediation.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) {
    return (
      <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6">
        <p className="text-sm text-[var(--cf-text-secondary)]">
          Loading remediation policy...
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-[var(--cf-border)] bg-[var(--cf-surface)] p-6">
      <div className="mb-6">
        <p className="text-sm font-medium text-blue-400">
          Controlled remediation
        </p>

        <h2 className="mt-1 text-xl font-semibold text-[var(--cf-text)]">
          Human-approved remediation
        </h2>

        <p className="mt-2 max-w-4xl text-sm leading-6 text-[var(--cf-text-secondary)]">
          AI-assisted recommendations remain inside a
          deterministic policy boundary. Production-changing
          actions require explicit human approval before
          execution.
        </p>
      </div>

      {error && (
        <div className="mb-5 rounded-lg border border-rose-700/50 bg-rose-950/30 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-5">
          <h3 className="text-sm font-semibold text-[var(--cf-text)]">
            Policy boundary
          </h3>

          <div className="mt-4 space-y-3">
            {data?.available_actions.map((action) => (
              <div
                key={action.action}
                className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-[var(--cf-text-secondary)]">
                      {actionLabel(action.action)}
                    </p>

                    <p className="mt-1 text-xs leading-5 text-[var(--cf-text-muted)]">
                      {action.description}
                    </p>
                  </div>

                  <span
                    className={`rounded-full border px-2.5 py-1 text-xs font-medium ${policyClass(action)}`}
                  >
                    {policyLabel(action)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-5">
          <h3 className="text-sm font-semibold text-[var(--cf-text)]">
            Create remediation proposal
          </h3>

          <div className="mt-4 space-y-4">
            <div>
              <label
                htmlFor="remediation-action"
                className="mb-2 block text-xs font-medium uppercase tracking-wide text-[var(--cf-text-muted)]"
              >
                Action
              </label>

              <select
                id="remediation-action"
                value={selectedAction}
                onChange={(event) =>
                  setSelectedAction(
                    event.target.value as RemediationAction,
                  )
                }
                className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-3 py-2.5 text-sm text-[var(--cf-text-secondary)] outline-none focus:border-blue-500"
              >
                {data?.available_actions.map(
                  (action) => (
                    <option
                      key={action.action}
                      value={action.action}
                      disabled={
                        action.policy === "blocked"
                      }
                    >
                      {actionLabel(action.action)}
                      {action.human_approval_required
                        ? " — approval required"
                        : action.policy === "blocked"
                          ? " — blocked"
                          : " — allowed"}
                    </option>
                  ),
                )}
              </select>
            </div>

            {selectedAction ===
              "rerun_deployment" && (
              <div>
                <label
                  htmlFor="target-deployment-id"
                  className="mb-2 block text-xs font-medium uppercase tracking-wide text-[var(--cf-text-muted)]"
                >
                  Target deployment ID
                </label>

                <input
                  id="target-deployment-id"
                  value={targetDeploymentId}
                  onChange={(event) =>
                    setTargetDeploymentId(
                      event.target.value,
                    )
                  }
                  placeholder="Existing pending deployment ID"
                  className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-3 py-2.5 text-sm text-[var(--cf-text-secondary)] placeholder:text-[var(--cf-text-muted)] outline-none focus:border-blue-500"
                />
              </div>
            )}

            <div>
              <label
                htmlFor="remediation-reason"
                className="mb-2 block text-xs font-medium uppercase tracking-wide text-[var(--cf-text-muted)]"
              >
                Reason
              </label>

              <textarea
                id="remediation-reason"
                value={reason}
                onChange={(event) =>
                  setReason(event.target.value)
                }
                rows={3}
                placeholder="Explain why this remediation is being proposed."
                className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-3 py-2.5 text-sm text-[var(--cf-text-secondary)] placeholder:text-[var(--cf-text-muted)] outline-none focus:border-blue-500"
              />
            </div>

            {selectedPolicy && (
              <div
                className={`rounded-lg border p-4 text-sm ${policyClass(selectedPolicy)}`}
              >
                <p className="font-medium">
                  Policy decision:{" "}
                  {policyLabel(selectedPolicy)}
                </p>

                <p className="mt-1 text-xs opacity-80">
                  {selectedPolicy.description}
                </p>
              </div>
            )}

            <button
              type="button"
              onClick={() => void handlePreview()}
              disabled={
                actionLoading ||
                selectedPolicy?.policy === "blocked"
              }
              className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-[var(--cf-text)] transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {actionLoading
                ? "Processing..."
                : "Create remediation proposal"}
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-[var(--cf-text)]">
              Remediation audit trail
            </h3>

            <p className="mt-1 text-xs text-[var(--cf-text-muted)]">
              Every proposal remains tied to policy,
              approval, execution, and result state.
            </p>
          </div>

          <span className="rounded-full border border-[var(--cf-border)] px-3 py-1 text-xs text-[var(--cf-text-muted)]">
            {data?.proposals.length ?? 0} proposal
            {data?.proposals.length === 1 ? "" : "s"}
          </span>
        </div>

        {!data?.proposals.length ? (
          <div className="rounded-lg border border-dashed border-dashed border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-6 text-center text-sm text-[var(--cf-text-muted)]">
            No remediation proposals have been created
            for this incident.
          </div>
        ) : (
          <div className="space-y-4">
            {data.proposals.map((proposal) => (
              <div
                key={proposal.id}
                className="rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="font-medium text-[var(--cf-text-secondary)]">
                      {actionLabel(proposal.action)}
                    </p>

                    <p className="mt-1 text-xs text-[var(--cf-text-muted)]">
                      Proposal {proposal.id}
                    </p>
                  </div>

                  <span
                    className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusClass(proposal.status)}`}
                  >
                    {proposal.status}
                  </span>
                </div>

                <div className="mt-4 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                  <div>
                    <p className="text-[var(--cf-text-muted)]">
                      Policy
                    </p>
                    <p className="mt-1 text-[var(--cf-text-secondary)]">
                      {proposal.policy_decision}
                    </p>
                  </div>

                  <div>
                    <p className="text-[var(--cf-text-muted)]">
                      Proposed by
                    </p>
                    <p className="mt-1 text-[var(--cf-text-secondary)]">
                      {proposal.proposed_by}
                    </p>
                  </div>

                  <div>
                    <p className="text-[var(--cf-text-muted)]">
                      Approved by
                    </p>
                    <p className="mt-1 text-[var(--cf-text-secondary)]">
                      {proposal.approved_by ?? "—"}
                    </p>
                  </div>

                  <div>
                    <p className="text-[var(--cf-text-muted)]">
                      Created
                    </p>
                    <p className="mt-1 text-[var(--cf-text-secondary)]">
                      {formatDate(proposal.created_at)}
                    </p>
                  </div>
                </div>

                <div className="mt-4 rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-[var(--cf-text-muted)]">
                    Policy reasoning
                  </p>

                  <p className="mt-2 text-sm leading-6 text-[var(--cf-text-secondary)]">
                    {proposal.policy_reason}
                  </p>

                  {proposal.reason && (
                    <>
                      <p className="mt-4 text-xs font-medium uppercase tracking-wide text-[var(--cf-text-muted)]">
                        Operator reason
                      </p>

                      <p className="mt-2 text-sm leading-6 text-[var(--cf-text-secondary)]">
                        {proposal.reason}
                      </p>
                    </>
                  )}

                  {proposal.error && (
                    <div className="mt-4 rounded-lg border border-rose-700/50 bg-rose-950/30 p-3 text-sm text-rose-300">
                      {proposal.error}
                    </div>
                  )}

                  {proposal.rejection_reason && (
                    <div className="mt-4 rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] p-3 text-sm text-[var(--cf-text-secondary)]">
                      Rejection reason:{" "}
                      {proposal.rejection_reason}
                    </div>
                  )}
                </div>

                {proposalCanApprove(proposal) && (
                  <div className="mt-4 rounded-lg border border-amber-800/40 bg-amber-950/20 p-4">
                    <p className="text-sm font-medium text-amber-300">
                      Human approval required
                    </p>

                    <p className="mt-1 text-xs leading-5 text-amber-200/70">
                      This action cannot execute until an
                      operator explicitly approves it.
                    </p>

                    <div className="mt-4 flex flex-col gap-3">
                      <textarea
                        value={
                          rejectionReasons[
                            proposal.id
                          ] ?? ""
                        }
                        onChange={(event) =>
                          setRejectionReasons(
                            (current) => ({
                              ...current,
                              [proposal.id]:
                                event.target.value,
                            }),
                          )
                        }
                        rows={2}
                        placeholder="Required only when rejecting."
                        className="w-full rounded-lg border border-[var(--cf-border)] bg-[var(--cf-surface-2)] px-3 py-2.5 text-sm text-[var(--cf-text-secondary)] placeholder:text-[var(--cf-text-muted)] outline-none focus:border-blue-500"
                      />

                      <div className="flex flex-wrap gap-3">
                        <button
                          type="button"
                          onClick={() =>
                            void handleApprove(
                              proposal,
                            )
                          }
                          disabled={actionLoading}
                          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-[var(--cf-text)] hover:bg-emerald-500 disabled:opacity-50"
                        >
                          Approve remediation
                        </button>

                        <button
                          type="button"
                          onClick={() =>
                            void handleReject(
                              proposal,
                            )
                          }
                          disabled={actionLoading}
                          className="rounded-lg border border-rose-700/60 px-4 py-2 text-sm font-semibold text-rose-300 hover:bg-rose-950/40 disabled:opacity-50"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {proposalCanExecute(proposal) && (
                  <div className="mt-4 rounded-lg border border-blue-800/40 bg-blue-950/20 p-4">
                    <p className="text-sm font-medium text-blue-300">
                      Approved and ready to execute
                    </p>

                    <p className="mt-1 text-xs leading-5 text-blue-200/70">
                      Execution is still an explicit operator
                      action. Approval does not automatically
                      mutate production.
                    </p>

                    <button
                      type="button"
                      onClick={() =>
                        void handleExecute(
                          proposal,
                        )
                      }
                      disabled={actionLoading}
                      className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-[var(--cf-text)] hover:bg-blue-500 disabled:opacity-50"
                    >
                      Execute remediation
                    </button>
                  </div>
                )}

                {proposal.status === "SUCCEEDED" && (
                  <div className="mt-4 rounded-lg border border-emerald-700/40 bg-emerald-950/20 p-4">
                    <p className="text-sm font-medium text-emerald-300">
                      Remediation completed successfully
                    </p>

                    <p className="mt-1 text-xs text-emerald-200/70">
                      Executed{" "}
                      {formatDate(
                        proposal.executed_at,
                      )}
                    </p>
                  </div>
                )}

                {proposal.status === "FAILED" && (
                  <div className="mt-4 rounded-lg border border-rose-700/40 bg-rose-950/20 p-4">
                    <p className="text-sm font-medium text-rose-300">
                      Remediation execution failed
                    </p>

                    <p className="mt-1 text-xs text-rose-200/70">
                      Review the recorded error above and
                      the incident timeline.
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
