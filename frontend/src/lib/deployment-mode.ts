import type { Deployment } from "@/types/deployments";

export function executionModeLabel(mode: Deployment["execution_mode"]): string {
  if (mode === "simulated") return "Simulated";
  if (mode === "kubernetes") return "Kubernetes";
  return "Execution mode unknown";
}
