// Settings ▸ General toggle that mirrors the tidy confirmation's "Don't show this
// again" checkbox — both write the single global `tidyConfirmationSuppressed` flag,
// so dismissing the dialog once flips this switch and vice versa. Framed positively
// here: ON = confirm before tidying (default), OFF = tidy silently.

import { Switch } from "@radix-ui/themes";
import { useAtom } from "jotai";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { tidyConfirmationSuppressedAtom } from "~/components/sections/savedLayoutAtoms.ts";

import { SettingRow } from "./SettingRow.tsx";

export const TidyConfirmationSettingRow = (): ReactElement => {
  const [isSuppressed, setSuppressed] = useAtom(tidyConfirmationSuppressedAtom);
  return (
    <SettingRow
      title="Confirm before tidying panels"
      description="When you apply a layout that tidies, ask before closing the panels it doesn’t include."
    >
      <Switch
        checked={!isSuppressed}
        onCheckedChange={(checked) => setSuppressed(!checked)}
        data-testid={ElementIds.SETTINGS_TIDY_CONFIRMATION_SWITCH}
      />
    </SettingRow>
  );
};
