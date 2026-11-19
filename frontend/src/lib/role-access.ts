import type { CloudForgeRole } from "./auth";

const operatorRoles = ["platform-engineer", "sre"] as const;

export const dashboardProfiles = {
  "platform-engineer": {
    title: "Platform administration",
    description: "Manage the platform, review infrastructure approvals, and monitor delivery and operational health.",
  },
  sre: {
    title: "Reliability operations",
    description: "Track service health, investigate incidents, and manage authorized deployment recovery.",
  },
  developer: {
    title: "My project workspace",
    description: "Manage your projects, track infrastructure requests, and monitor your deployments.",
  },
} satisfies Record<CloudForgeRole, { title: string; description: string }>;

export function dashboardCapabilities(role: CloudForgeRole) {
  return {
    platformTelemetry: role !== "developer",
    accountCosts: role !== "developer",
    approvalQueue: role === "platform-engineer",
    administration: role === "platform-engineer",
  };
}

type NavigationItem = {
  href: string;
  label: string;
  icon: string;
  roles: readonly CloudForgeRole[];
  developerLabel?: string;
};

const allRoles = ["platform-engineer", "sre", "developer"] as const;
const navigation: { label: string; items: NavigationItem[] }[] = [
  { label: "Workspace", items: [
    { href: "/dashboard", label: "Overview", icon: "▦", roles: allRoles },
    { href: "/projects", label: "Projects", developerLabel: "My Projects", icon: "◈", roles: allRoles },
    { href: "/infrastructure", label: "Infrastructure", developerLabel: "Infrastructure Requests", icon: "⌘", roles: allRoles },
    { href: "/deployments", label: "Deployments", developerLabel: "My Deployments", icon: "⇧", roles: allRoles },
    { href: "/finops", label: "FinOps", icon: "$", roles: operatorRoles },
    { href: "/project-costs", label: "Project FinOps", icon: "$", roles: ["developer"] },
    { href: "/administration", label: "Administration", icon: "◇", roles: ["platform-engineer"] },
  ] },
  { label: "Reliability", items: [
    { href: "/observability", label: "Observability", developerLabel: "Project Monitoring", icon: "◉", roles: allRoles },
    { href: "/slo", label: "SLO & Error Budget", icon: "◒", roles: operatorRoles },
    { href: "/incidents", label: "AIOps Incidents", icon: "⚡", roles: operatorRoles },
    { href: "/anomalies", label: "Anomaly Detection", icon: "◌", roles: operatorRoles },
  ] },
];

export function navigationFor(role: CloudForgeRole) {
  return navigation.map(({ label, items }) => ({
    label,
    items: items.filter((item) => item.roles.includes(role)).map((item) => ({
      ...item,
      label: role === "developer" ? item.developerLabel ?? item.label : item.label,
    })),
  })).filter(({ items }) => items.length > 0);
}

export function canAccessPage(role: CloudForgeRole, path: string): boolean {
  if (path === "/" || path === "/access-denied") return true;
  return navigation.some(({ items }) => items.some(({ href, roles }) =>
    (path === href || path.startsWith(`${href}/`)) && roles.includes(role),
  ));
}

export function pageDecision(role: CloudForgeRole | null, path: string): "sign-in" | "allow" | "deny" {
  return role === null ? "sign-in" : canAccessPage(role, path) ? "allow" : "deny";
}

export function selectAuthorizedProject<T extends { id: string }>(projects: T[], requested?: string | null): T | undefined {
  return requested ? projects.find(({ id }) => id === requested) : projects[0];
}

export function dashboardDestination(role: CloudForgeRole, next: string): string {
  const path = next.split(/[?#]/, 1)[0];
  return canAccessPage(role, path) ? next : "/dashboard";
}

export function canWriteProject(role: CloudForgeRole | undefined, level: string | undefined): boolean {
  return role === "platform-engineer" || ((role === "developer" || role === "sre") &&
    (level === "owner" || level === "maintainer"));
}

export function canExecuteTerraform(role: CloudForgeRole | undefined): boolean {
  return role === "platform-engineer";
}
