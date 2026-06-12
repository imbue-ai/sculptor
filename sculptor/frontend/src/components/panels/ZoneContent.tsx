import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { activePanelInZoneAtom } from "~/components/panels/atoms.ts";
import type { ZoneId } from "~/components/panels/types.ts";

import styles from "./ZoneContent.module.scss";

type ZoneContentProps = {
  zoneId: ZoneId;
};

const ZoneContentInner = ({ zoneId }: ZoneContentProps): ReactElement | null => {
  const panelDef = useAtomValue(activePanelInZoneAtom(zoneId));

  if (!panelDef) return null;

  const PanelComponent = panelDef.component;

  return (
    <div className={styles.zoneContent} data-zone-id={zoneId} tabIndex={-1}>
      <PanelComponent />
    </div>
  );
};

export const ZoneContent = memo(ZoneContentInner);
ZoneContent.displayName = "ZoneContent";
