import { Flex } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { PanelBottom, PanelLeft, PanelRight, ScanLine } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { keybindingsMapAtom } from "~/common/keybindings/atoms.ts";
import type { KeybindingId } from "~/common/keybindings/types.ts";
import { formatShortcutForDisplay } from "~/common/ShortcutUtils.ts";
import { DevModeIndicator } from "~/components/DevModeIndicator.tsx";
import { focusModeActiveAtom, sideHasPanelsAtom, zenModeActiveAtom } from "~/components/panels/atoms.ts";
import { useFocusMode, useSideToggle } from "~/components/panels/hooks.ts";
import type { LayoutSide } from "~/components/panels/types.ts";
import { TooltipIconButton } from "~/components/TooltipIconButton.tsx";
import { VersionDisplay } from "~/components/VersionDisplay.tsx";

import styles from "./BottomBar.module.scss";

type SideToggleButtonProps = {
  side: LayoutSide;
};

const SIDE_CONFIG = {
  left: {
    icon: PanelLeft,
    label: "left sidebar",
    testId: ElementIds.SIDE_TOGGLE_LEFT,
    keybindingId: "toggle_left_panel",
  },
  bottom: {
    icon: PanelBottom,
    label: "bottom panel",
    testId: ElementIds.SIDE_TOGGLE_BOTTOM,
    keybindingId: "toggle_bottom_panel",
  },
  right: {
    icon: PanelRight,
    label: "right sidebar",
    testId: ElementIds.SIDE_TOGGLE_RIGHT,
    keybindingId: "toggle_right_panel",
  },
} as const satisfies Record<
  LayoutSide,
  { icon: typeof PanelLeft; label: string; testId: string; keybindingId: KeybindingId }
>;

const SideToggleButton = ({ side }: SideToggleButtonProps): ReactElement => {
  const { isVisible, toggle } = useSideToggle(side);
  const hasPanels = useAtomValue(sideHasPanelsAtom(side));
  const { icon: Icon, label, testId, keybindingId } = SIDE_CONFIG[side];
  const keybindingsMap = useAtomValue(keybindingsMapAtom);
  const shortcut = formatShortcutForDisplay(keybindingsMap[keybindingId].binding ?? undefined);

  const isEmpty = !hasPanels;
  const tooltipText = isEmpty
    ? "Panel is empty"
    : `${isVisible ? "Hide" : "Show"} ${label}${shortcut ? ` (${shortcut})` : ""}`;

  return (
    // `aria-disabled` mirrors the `isEmpty` gate that nulls out `onClick`, so an
    // empty-panel toggle reads as disabled to the actionability contract and to
    // assistive tech — not just visually via `toggleDisabled`. Native `disabled`
    // is avoided deliberately: it would suppress the "Panel is empty" tooltip (SCU-1215).
    <TooltipIconButton
      tooltipText={tooltipText}
      aria-disabled={isEmpty}
      onClick={isEmpty ? undefined : toggle}
      className={isEmpty ? styles.toggleDisabled : isVisible ? styles.toggleActive : styles.toggleInactive}
      data-testid={testId}
    >
      <Icon size={14} />
    </TooltipIconButton>
  );
};

const FocusModeButton = (): ReactElement => {
  const isFocusModeActive = useAtomValue(focusModeActiveAtom);
  const { toggleFocusMode } = useFocusMode();
  const keybindingsMap = useAtomValue(keybindingsMapAtom);
  const shortcut = formatShortcutForDisplay(keybindingsMap["focus_mode"].binding ?? undefined);
  const label = isFocusModeActive ? "Exit focus mode" : "Enter focus mode";
  const tooltipText = `${label}${shortcut ? ` (${shortcut})` : ""}`;

  return (
    <TooltipIconButton
      tooltipText={tooltipText}
      onClick={toggleFocusMode}
      className={isFocusModeActive ? styles.toggleActive : styles.toggleInactive}
      data-testid={ElementIds.FOCUS_MODE_BUTTON}
    >
      <ScanLine size={14} />
    </TooltipIconButton>
  );
};

export const BottomBar = (): ReactElement | null => {
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  if (isZenModeActive) return null;

  return (
    <Flex className={styles.bottomBar} align="center" px="3" py="2" data-testid={ElementIds.BOTTOM_BAR}>
      <Flex align="center" gapX="3" flexBasis="0" flexGrow="1" justify="start">
        <SideToggleButton side="left" />
        <SideToggleButton side="bottom" />
        <SideToggleButton side="right" />
        <FocusModeButton />
      </Flex>
      <Flex align="center" flexBasis="0" flexGrow="1" justify="center">
        <DevModeIndicator />
      </Flex>
      <Flex align="center" gap="3" flexBasis="0" flexGrow="1" justify="end">
        <VersionDisplay />
      </Flex>
    </Flex>
  );
};
