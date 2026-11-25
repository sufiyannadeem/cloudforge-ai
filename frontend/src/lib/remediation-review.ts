import type { RemediationProposal } from "@/types/incidents";
export type ReviewIdentity = { username: string; role: string } | null;
const fresh = (p: RemediationProposal) => Boolean(p.recommendation_version && p.action_fingerprint && p.expires_at && Date.parse(p.expires_at) > Date.now());
export function canApproveRecommendation(p: RemediationProposal, user: ReviewIdentity) {
  const target = p.state_snapshot?.target;
  const requester = target && typeof target === "object" ? (target as Record<string, unknown>).created_by : undefined;
  return user?.role === "platform-engineer" && user.username !== p.proposed_by && user.username !== requester && p.status === "PENDING_APPROVAL" && fresh(p);
}
export function canRejectRecommendation(p: RemediationProposal, user: ReviewIdentity) {
  return Boolean(user && ["platform-engineer", "sre"].includes(user.role) && ["PENDING_APPROVAL", "APPROVED"].includes(p.status));
}
export function canExecuteRecommendation(p: RemediationProposal, user: ReviewIdentity) {
  return p.execution_supported !== false && user?.role === "platform-engineer" && p.approved_role === "platform-engineer" && Boolean(p.approved_by) && p.approved_by !== p.proposed_by && p.status === "APPROVED" && fresh(p);
}
