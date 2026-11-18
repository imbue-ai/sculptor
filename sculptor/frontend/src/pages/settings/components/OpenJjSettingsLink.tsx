import { Link } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";
import { SettingsSection } from "~/pages/settings/sections.ts";

export const OpenJjSettingsLink = (): ReactElement => {
  const openSettings = useOpenSettings();
  return (
    <Link
      href="#"
      size="1"
      onClick={(e) => {
        e.preventDefault();
        openSettings(SettingsSection.JJ);
      }}
    >
      Open Jujutsu settings
    </Link>
  );
};
