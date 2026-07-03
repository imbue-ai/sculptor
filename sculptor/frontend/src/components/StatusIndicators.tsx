import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { VersionPopover } from "~/components/VersionPopover.tsx";

// Carries only the version popover. Don't add a ReportProblemPopover here — the
// sidebar footer's "Report a bug" button (SIDEBAR_REPORT_BUG) binds the same
// shared reportProblemAtom, so a second popover would open a duplicate dialog.
export const StatusIndicators = (): ReactElement => {
  return (
    <Flex align="center" gap="2">
      <VersionPopover />
    </Flex>
  );
};
