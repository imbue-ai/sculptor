import * as Dialog from "@radix-ui/react-dialog";
import { Cross1Icon } from "@radix-ui/react-icons";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
import { Badge, Box, Flex, IconButton, Separator, Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useMemo } from "react";

import { ElementIds } from "../api";
import { keybindingsAtom } from "../common/keybindings/atoms.ts";
import { CATEGORY_DISPLAY_NAMES, CATEGORY_ORDER, type KeybindingCategory } from "../common/keybindings/types.ts";
import { formatShortcutForDisplay } from "../common/ShortcutUtils.ts";
import { useHelpDialog } from "../common/state/hooks/useHelpDialog.ts";
import styles from "./KeyboardShortcutsDialog.module.scss";

type ShortcutRowProps = {
  label: string;
  shortcut: string;
  testId?: string;
};

const ShortcutRow = ({ label, shortcut, testId }: ShortcutRowProps): ReactElement => (
  <div className={styles.shortcutRow} data-testid={testId}>
    <Text className={styles.shortcutLabel}>{label}</Text>
    <Badge size="1" variant="soft">
      {shortcut}
    </Badge>
  </div>
);

type ShortcutSectionProps = {
  title: string;
  shortcuts: Array<ShortcutRowProps>;
};

const ShortcutSection = ({ title, shortcuts }: ShortcutSectionProps): ReactElement => (
  <Flex direction="column" gap="1">
    <Text className={styles.sectionTitle}>{title}</Text>
    {shortcuts.map(({ label, shortcut, testId }) => (
      <ShortcutRow key={label} label={label} shortcut={shortcut} testId={testId} />
    ))}
  </Flex>
);

export const KeyboardShortcutsDialog = (): ReactElement => {
  const { isHelpDialogOpen, hideHelpDialog } = useHelpDialog();
  const keybindings = useAtomValue(keybindingsAtom);

  const sections = useMemo((): Array<ShortcutSectionProps> => {
    const grouped = new Map<KeybindingCategory, Array<ShortcutRowProps>>();

    for (const kb of keybindings) {
      if (kb.binding == null) continue;
      const existing = grouped.get(kb.category) ?? [];
      existing.push({
        label: kb.name,
        shortcut: formatShortcutForDisplay(kb.binding),
        testId: `${ElementIds.HELP_SHORTCUT_ROW}-${kb.id}`,
      });
      grouped.set(kb.category, existing);
    }

    const result: Array<ShortcutSectionProps> = [];
    for (const category of CATEGORY_ORDER) {
      const shortcuts = grouped.get(category);
      if (!shortcuts || shortcuts.length === 0) continue;
      result.push({ title: CATEGORY_DISPLAY_NAMES[category], shortcuts });
    }
    return result;
  }, [keybindings]);

  return (
    <Dialog.Root open={isHelpDialogOpen} onOpenChange={(open) => !open && hideHelpDialog()}>
      <VisuallyHidden>
        <Dialog.Title>Help</Dialog.Title>
      </VisuallyHidden>
      <Dialog.Overlay className={styles.overlay} />
      <Dialog.Content className={styles.dialogContainer} data-testid={ElementIds.KEYBOARD_SHORTCUTS_DIALOG}>
        <Box className={styles.panel}>
          <Box position="absolute" top="22px" right="4">
            <Dialog.Close asChild>
              <IconButton variant="ghost" size="1" aria-label="Close">
                <Cross1Icon />
              </IconButton>
            </Dialog.Close>
          </Box>

          <Flex direction="column" className={styles.body} gap="4">
            <Text size="4" weight="bold">
              Help
            </Text>

            <Separator size="4" />

            <Text size="3" weight="bold">
              Keyboard Shortcuts
            </Text>

            {sections.map((section, i) => (
              <Box key={section.title}>
                {i > 0 && <Separator size="4" mb="4" />}
                <ShortcutSection title={section.title} shortcuts={section.shortcuts} />
              </Box>
            ))}
          </Flex>
        </Box>
      </Dialog.Content>
    </Dialog.Root>
  );
};
