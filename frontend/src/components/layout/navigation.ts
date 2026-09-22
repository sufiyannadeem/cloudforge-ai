export interface NavigationItem {
  label: string;
  href: string;
  icon: string;
}

export const navigationItems: NavigationItem[] = [
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
  {
    label: "AI-Ops Incidents",
    href: "/incidents",
    icon: "⚡",
  },
];
