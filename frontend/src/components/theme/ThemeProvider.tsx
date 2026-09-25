"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";

export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

interface ThemeContextValue {
  theme: ThemeMode;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: ThemeMode) => void;
}

const ThemeContext =
  createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = "cloudforge-theme";

let listeners: Array<() => void> = [];

function subscribe(callback: () => void) {
  listeners.push(callback);

  return () => {
    listeners = listeners.filter(
      (listener) => listener !== callback,
    );
  };
}

function getStoredTheme(): ThemeMode {
  if (typeof window === "undefined") {
    return "system";
  }

  const value =
    window.localStorage.getItem(STORAGE_KEY);

  if (
    value === "light" ||
    value === "dark" ||
    value === "system"
  ) {
    return value;
  }

  return "system";
}

function getServerTheme(): ThemeMode {
  return "system";
}

function getSystemTheme(): ResolvedTheme {
  if (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)")
      .matches
  ) {
    return "dark";
  }

  return "light";
}

function resolveTheme(
  theme: ThemeMode,
): ResolvedTheme {
  return theme === "system"
    ? getSystemTheme()
    : theme;
}

function applyTheme(
  theme: ThemeMode,
): ResolvedTheme {
  const resolved = resolveTheme(theme);

  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme =
      resolved;

    document.documentElement.classList.toggle(
      "dark",
      resolved === "dark",
    );

    document.documentElement.style.colorScheme =
      resolved;
  }

  return resolved;
}

function saveTheme(theme: ThemeMode) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(
    STORAGE_KEY,
    theme,
  );

  applyTheme(theme);

  for (const listener of listeners) {
    listener();
  }
}

function subscribeToSystemTheme(
  callback: () => void,
) {
  if (typeof window === "undefined") {
    return () => {};
  }

  const mediaQuery = window.matchMedia(
    "(prefers-color-scheme: dark)",
  );

  mediaQuery.addEventListener(
    "change",
    callback,
  );

  return () => {
    mediaQuery.removeEventListener(
      "change",
      callback,
    );
  };
}

export function ThemeProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const theme = useSyncExternalStore(
    subscribe,
    getStoredTheme,
    getServerTheme,
  );

  const resolvedTheme: ResolvedTheme = useSyncExternalStore(
    subscribeToSystemTheme,
    () => resolveTheme(theme),
    () => "light" as ResolvedTheme,
  );

  const setTheme = useCallback(
    (nextTheme: ThemeMode) => {
      saveTheme(nextTheme);
    },
    [],
  );

  if (typeof document !== "undefined") {
    const current =
      document.documentElement.dataset.theme;

    if (current !== resolvedTheme) {
      applyTheme(theme);
    }
  }

  const value = useMemo(
    () => ({
      theme,
      resolvedTheme,
      setTheme,
    }),
    [theme, resolvedTheme, setTheme],
  );

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);

  if (!context) {
    throw new Error(
      "useTheme must be used inside ThemeProvider",
    );
  }

  return context;
}
