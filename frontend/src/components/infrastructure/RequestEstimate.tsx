"use client";

import { useEffect, useState } from "react";
import type { PlanDetails } from "@/types/infrastructure";

const scopes = {
  aws_instance: "EC2 compute only",
  aws_db_instance: "RDS instance only",
  aws_eks_node_group: "EKS workers only at desired capacity",
};

export default function RequestEstimate({ plan }: { plan: PlanDetails }) {
  const { pricing_basis: basis, region } = plan;
  const [estimate, setEstimate] = useState<{ monthly: number | null }>();
  useEffect(() => {
    if (!basis) return;
    const controller = new AbortController();
    const parts = [basis.resource_type, region, basis.unit].map(encodeURIComponent).join("/");
    void fetch(`/api/proxy/finops/api/v1/terraform/request-estimate/${parts}`, {
      cache: "no-store", signal: controller.signal,
    }).then(async (response) => {
      const data: { unit_monthly_usd?: unknown } = response.ok ? await response.json() : {};
      const rate = data.unit_monthly_usd;
      const monthly = typeof rate === "number" && rate >= 0 ? rate * basis.quantity : NaN;
      if (!controller.signal.aborted) setEstimate({ monthly: Number.isFinite(monthly) ? monthly : null });
    }).catch(() => {
      if (!controller.signal.aborted) setEstimate({ monthly: null });
    });
    return () => controller.abort();
  }, [basis, region]);

  if (!basis || estimate?.monthly === null) return <p>Cost estimate unavailable.</p>;
  if (!estimate) return <p role="status">Loading cost estimate…</p>;
  return <p>
    Estimated {new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(estimate.monthly)} / month
    {" · "}{scopes[basis.resource_type]}. Excludes other infrastructure and usage charges.
  </p>;
}
