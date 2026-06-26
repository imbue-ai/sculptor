import { Flex, SegmentedControl } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";

import { effectiveHomeViewIdAtom, homeViewOptionsAtom, selectedHomeViewAtom } from "./homeViews.ts";

/**
 * Segmented control that switches the homepage body between the built-in
 * recent-workspaces view and any plugin-contributed home views. Bound to the
 * persisted selection; the active item reflects the *effective* view, so a
 * selection whose plugin has gone away shows the built-in view as active.
 */
export const HomeViewSwitcher = (): ReactElement => {
  const options = useAtomValue(homeViewOptionsAtom);
  const effectiveId = useAtomValue(effectiveHomeViewIdAtom);
  const setSelected = useSetAtom(selectedHomeViewAtom);

  return (
    <SegmentedControl.Root value={effectiveId} onValueChange={setSelected} size="2">
      {options.map(({ id, title, icon: Icon }) => (
        <SegmentedControl.Item key={id} value={id}>
          <Flex align="center" gap="2">
            {Icon ? <Icon /> : null}
            {title}
          </Flex>
        </SegmentedControl.Item>
      ))}
    </SegmentedControl.Root>
  );
};
