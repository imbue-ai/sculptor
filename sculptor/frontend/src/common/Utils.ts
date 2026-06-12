import { useEffect, useState } from "react";
import { typeid } from "typeid-js";

import { useThemeAppearance } from "./state/hooks/useThemeBuilder.ts";

export const mergeClasses = (...classes: ReadonlyArray<string | undefined>): string => {
  return classes.filter((c) => c).join(" ");
};

export const optional = <T>(condition: boolean, value: T): T | undefined => {
  return condition ? value : undefined;
};

export const neutral = "gray" as const;

export const makeRequestId = (): string => {
  return typeid("rqst").toString();
};

type Theme = "light" | "dark";

export const useResolvedTheme = (): Theme => {
  const configTheme = useThemeAppearance();
  const [systemTheme, setSystemTheme] = useState<Theme>("light");

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

    const updateSystemTheme = (): void => {
      setSystemTheme(mediaQuery.matches ? "dark" : "light");
    };

    // Set initial system theme
    updateSystemTheme();

    // Listen for system theme changes
    mediaQuery.addEventListener("change", updateSystemTheme);

    return (): void => mediaQuery.removeEventListener("change", updateSystemTheme);
  }, []);

  // Resolve theme based on user preference
  if (configTheme === "system") {
    return systemTheme;
  }

  return (configTheme as Theme) || "light";
};
