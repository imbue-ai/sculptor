import { TextField } from "@radix-ui/themes";
import { type ReactElement, useEffect, useState } from "react";

import { ElementIds } from "~/api";
import { type ToastContent, ToastType } from "~/common/state/atoms/toasts.ts";

import { SettingRow } from "./SettingRow.tsx";

const DEFAULT_BACKEND_READINESS_TIMEOUT_SECONDS = 60;

type CustomBackendSectionProps = {
  setToast: (toast: ToastContent | null) => void;
};

export const CustomBackendSection = ({ setToast }: CustomBackendSectionProps): ReactElement | null => {
  const [customBackendCommand, setCustomBackendCommand] = useState("");
  const [backendReadinessTimeout, setBackendReadinessTimeout] = useState(DEFAULT_BACKEND_READINESS_TIMEOUT_SECONDS);

  useEffect(() => {
    let isIgnored = false;
    window.sculptor?.getCustomBackendSettings().then((settings) => {
      if (isIgnored) return;
      setCustomBackendCommand(settings.customBackendCommand);
      setBackendReadinessTimeout(settings.backendReadinessTimeout);
    });
    return (): void => {
      isIgnored = true;
    };
  }, []);

  if (!window.sculptor) {
    return null;
  }

  const saveCommand = (value: string): void => {
    window.sculptor?.setCustomBackendSettings({ customBackendCommand: value });
    setToast({ type: ToastType.SUCCESS, title: "Custom backend command saved. Restart required." });
  };

  const saveTimeout = (value: string): void => {
    const num = Number(value);

    if (!isNaN(num) && num > 0) {
      window.sculptor?.setCustomBackendSettings({ backendReadinessTimeout: num });
      setToast({ type: ToastType.SUCCESS, title: "Backend readiness timeout saved. Restart required." });
    }
  };

  return (
    <>
      <SettingRow
        title="Custom Backend Command"
        description="Shell command to launch the backend. Leave empty for default local mode. Requires restart."
      >
        <TextField.Root
          value={customBackendCommand}
          onChange={(e) => setCustomBackendCommand(e.target.value)}
          onBlur={(e) => saveCommand(e.target.value)}
          placeholder="e.g., docker run ..."
          data-testid={ElementIds.SETTINGS_CUSTOM_BACKEND_COMMAND}
          style={{ minWidth: "300px" }}
        />
      </SettingRow>
      <SettingRow
        title="Backend Readiness Timeout (seconds)"
        description="How long to wait for the backend to start. Only applies when using a custom backend command."
      >
        <TextField.Root
          type="number"
          value={String(backendReadinessTimeout)}
          onChange={(e) => setBackendReadinessTimeout(Number(e.target.value))}
          onBlur={(e) => saveTimeout(e.target.value)}
          data-testid={ElementIds.SETTINGS_BACKEND_READINESS_TIMEOUT}
          style={{ minWidth: "100px" }}
        />
      </SettingRow>
    </>
  );
};
