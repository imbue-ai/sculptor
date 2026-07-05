import { useEffect, useState } from "react";

import { useThemeAppearance } from "./useThemeBuilder.ts";

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

    updateSystemTheme();
    mediaQuery.addEventListener("change", updateSystemTheme);

    return (): void => mediaQuery.removeEventListener("change", updateSystemTheme);
  }, []);

  if (configTheme === "system") {
    return systemTheme;
  }

  return configTheme;
};
