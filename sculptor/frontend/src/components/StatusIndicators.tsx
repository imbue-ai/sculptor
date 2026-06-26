import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { VersionPopover } from "~/components/VersionPopover.tsx";

// The sidebar footer already renders the dedicated "Report a bug" button
// (SIDEBAR_REPORT_BUG), so this only carries the version popover. It previously
// rendered a second ReportProblemPopover, which — bound to the same shared
// reportProblemAtom — opened a duplicate dialog alongside the sidebar one.
export const StatusIndicators = (): ReactElement => {
  return (
    <Flex align="center" gap="2">
      <VersionPopover />
    </Flex>
  );
};
