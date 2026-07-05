import { useAtom } from "jotai";
import { useCallback } from "react";

import { tanstackDevtoolsEnabledAtom } from "../../../common/state/atoms/devPanel.ts";

type UseTanstackDevtoolsResult = {
  isEnabled: boolean;
  handleCheckedChange: (enabled: boolean) => void;
};

export const useTanstackDevtools = (): UseTanstackDevtoolsResult => {
  const [isEnabled, setIsEnabled] = useAtom(tanstackDevtoolsEnabledAtom);

  const handleCheckedChange = useCallback(
    (enabled: boolean): void => {
      setIsEnabled(enabled);
    },
    [setIsEnabled],
  );

  return { isEnabled, handleCheckedChange };
};
