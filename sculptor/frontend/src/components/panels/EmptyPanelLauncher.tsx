import { Button, Text } from "@radix-ui/themes";
import { useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useMemo } from "react";

import { addPanelTargetZoneAtom } from "~/components/panels/addPanelAtoms.ts";
import type { QuickAddItem } from "~/components/panels/quickAdd.ts";
import { pickQuickAdd } from "~/components/panels/quickAdd.ts";
import { useUnplacedStaticPanels } from "~/components/panels/sectionHooks.ts";
import type { ZoneId } from "~/components/panels/types.ts";
import { useAddPanelMenu } from "~/pages/workspace/panels/useAddPanelMenu.ts";

import styles from "./EmptyPanelLauncher.module.scss";

// Only the highest-priority Quick add shortcuts are shown; the rest remain
// reachable through the full Add Panel palette.
const QUICK_ADD_LIMIT = 5;

type EmptyPanelLauncherProps = {
  /** The section this empty state belongs to — where Quick add / the palette add panels. */
  zone: ZoneId;
  /** Optional heading shown above the launcher (e.g. to explain an empty split half). */
  heading?: string;
};

const itemLabel = (item: QuickAddItem): string => {
  if (item.kind === "create-terminal") return "New terminal";
  if (item.kind === "create-agent") return "New agent";
  return item.panel.displayName;
};

/**
 * The empty-section state: an "Add a panel…" button that opens the full Add
 * Panel palette (cmd+k) scoped to this section, over a "Quick add" list of the
 * create actions and every panel not currently open anywhere. The section's
 * tab-strip "+" opens the same palette.
 */
export const EmptyPanelLauncher = ({ zone, heading }: EmptyPanelLauncherProps): ReactElement => {
  const menu = useAddPanelMenu(zone);
  const unplacedPanels = useUnplacedStaticPanels();
  const openPalette = useSetAtom(addPanelTargetZoneAtom);
  const items = useMemo(() => pickQuickAdd(unplacedPanels).slice(0, QUICK_ADD_LIMIT), [unplacedPanels]);

  const onSelect = (item: QuickAddItem): void => {
    if (item.kind === "create-terminal") menu.createTerminal();
    else if (item.kind === "create-agent") menu.createAgent();
    else menu.openPanel(item.panel.id);
  };

  return (
    <div className={styles.launcher}>
      <div className={styles.quick}>
        {heading !== undefined && (
          <Text size="1" color="gray" className={styles.splitHint}>
            {heading}
          </Text>
        )}
        <button
          type="button"
          className={styles.browse}
          onClick={() => openPalette(zone)}
          data-testid="empty-panel-browse"
        >
          Add panel
        </button>
        <Text size="1" color="gray" className={styles.heading}>
          Quick add
        </Text>
        <div className={styles.quickList}>
          {items.map((item, index) => (
            <Button
              key={item.kind === "panel" ? item.panel.id : `${item.kind}-${index}`}
              variant="soft"
              color="gray"
              size="1"
              onClick={() => onSelect(item)}
            >
              {itemLabel(item)}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
};
