export interface NavigationItem {
  label: string;
  href: string;
  icon: string;
}

export interface NavigationGroup {
  label: string;
  items: NavigationItem[];
}

export const navigationGroups: NavigationGroup[] = [
  {
    label: "Platform",
    items: [
      {
        label: "Overview",
        href: "/dashboard",
        icon: "▦",
      },
      {
        label: "Projects",
        href: "/projects",
        icon: "◈",
      },
      {
        label: "Infrastructure",
        href: "/infrastructure",
        icon: "⌘",
      },
      {
        label: "Deployments",
        href: "/deployments",
        icon: "⇧",
      },
    ],
  },
  {
    label: "Reliability & AI",
    items: [
      {
        label: "Observability",
        href: "/observability",
        icon: "◉",
      },
      {
        label: "SLO & Error Budget",
        href: "/slo",
        icon: "◒",
      },
      {
        label: "AI-Ops Incidents",
        href: "/incidents",
        icon: "⚡",
      },
      {
        label: "Anomaly Detection",
        href: "/anomalies",
        icon: "◌",
      },
    ],
  },
];
