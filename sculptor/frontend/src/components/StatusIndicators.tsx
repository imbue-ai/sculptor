import { Flex } from "@radix-ui/themes";
import { Bug } from "lucide-react";
import type { ReactElement } from "react";

import { ReportProblemPopover } from "~/components/ReportProblemPopover.tsx";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import { VersionPopover } from "~/components/VersionPopover.tsx";

import styles from "./StatusIndicators.module.scss";

export const StatusIndicators = (): ReactElement => {
  return (
    <Flex align="center" gap="2">
      <ReportProblemPopover>
        <TooltipIconButton tooltipText="Report a problem" className={styles.bugButton} size="1">
          <Bug size={14} />
        </TooltipIconButton>
      </ReportProblemPopover>
      <VersionPopover />
    </Flex>
  );
};
