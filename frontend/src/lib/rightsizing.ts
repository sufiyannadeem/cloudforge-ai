import type { OptimizationFinding } from "@/types/finops";

/**
 * FinOps → Infrastructure bridge.
 *
 * A FinOps rightsizing finding never mutates AWS. It is turned into URL
 * parameters that pre-fill a CloudForge resource request on /infrastructure,
 * which then goes through the normal Terraform plan → hash → human approval
 * gate. The saving rationale travels with the request so the Terraform plan
 * can be traced back to the recommendation that triggered it.
 */

export const RIGHTSIZING_PATH = "/infrastructure";

const INSTANCE_TYPE_PATTERN = /^[a-z][a-z0-9-]*\.[a-z0-9]+$/;

export interface RightsizingRequest {
  resourceId: string;
  fromInstanceType: string;
  toInstanceType: string;
  monthlySavingsUsd: number;
  rationale: string;
}

export function isValidInstanceType(value: unknown): value is string {
  return typeof value === "string" && INSTANCE_TYPE_PATTERN.test(value);
}

/** Returns a request only for actionable EC2 downsizing findings. */
export function getRightsizingRequest(
  finding: OptimizationFinding,
): RightsizingRequest | null {
  if (finding.domain !== "ec2") {
    return null;
  }

  const from = finding.evidence?.instance_type;
  const to = finding.evidence?.target_instance;

  if (!isValidInstanceType(from) || !isValidInstanceType(to) || from === to) {
    return null;
  }

  return {
    resourceId: finding.resource_id,
    fromInstanceType: from,
    toInstanceType: to,
    monthlySavingsUsd: finding.potential_monthly_savings_usd,
    rationale: finding.recommendation,
  };
}

export function buildRightsizingHref(request: RightsizingRequest): string {
  const params = new URLSearchParams({
    rightsize: "1",
    resource: request.resourceId,
    from: request.fromInstanceType,
    to: request.toInstanceType,
    saving: String(request.monthlySavingsUsd),
    rationale: request.rationale,
  });

  return `${RIGHTSIZING_PATH}?${params.toString()}`;
}

/** Parses and validates query parameters; returns null if absent/invalid. */
export function parseRightsizingParams(
  search: string,
): RightsizingRequest | null {
  const params = new URLSearchParams(search);

  if (params.get("rightsize") !== "1") {
    return null;
  }

  const from = params.get("from");
  const to = params.get("to");

  if (!isValidInstanceType(from) || !isValidInstanceType(to)) {
    return null;
  }

  const saving = Number(params.get("saving"));

  return {
    resourceId: (params.get("resource") ?? "").slice(0, 200),
    fromInstanceType: from,
    toInstanceType: to,
    monthlySavingsUsd: Number.isFinite(saving) && saving > 0 ? saving : 0,
    rationale: (params.get("rationale") ?? "").slice(0, 500),
  };
}

/** Description stored on the new resource so the plan links back to FinOps. */
export function rightsizingDescription(request: RightsizingRequest): string {
  const saving =
    request.monthlySavingsUsd > 0
      ? ` Estimated saving: $${request.monthlySavingsUsd.toFixed(2)}/month.`
      : "";

  return (
    `FinOps rightsizing: ${request.fromInstanceType} → ${request.toInstanceType} ` +
    `(source ${request.resourceId || "unknown"}).${saving} ${request.rationale}`
  ).trim();
}
