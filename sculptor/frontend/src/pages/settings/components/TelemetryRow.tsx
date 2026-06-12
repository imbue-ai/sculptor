import { AlertDialog, Button, Flex, Spinner, Switch } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { posthog } from "posthog-js";
import { type ReactElement, useState } from "react";

import { ElementIds, setTelemetry } from "~/api";
import { isTelemetryEnabledAtom, userConfigAtom, userEmailAtom } from "~/common/state/atoms/userConfig.ts";
import { applyTelemetryConsent } from "~/common/Telemetry.ts";

import { type ToastContent, ToastType } from "../../../components/Toast.tsx";
import { SettingRow } from "./SettingRow.tsx";

type TelemetryRowProps = {
  setToast: (toast: ToastContent) => void;
};

type DialogState = "closed" | "open" | "applying";

export const TelemetryRow = ({ setToast }: TelemetryRowProps): ReactElement => {
  const isEnabled = useAtomValue(isTelemetryEnabledAtom);
  const userEmail = useAtomValue(userEmailAtom);
  const setUserConfig = useSetAtom(userConfigAtom);

  const [dialogState, setDialogState] = useState<DialogState>("closed");
  const [isOptingIn, setIsOptingIn] = useState(false);
  const isDialogOpen = dialogState !== "closed";
  const isApplying = dialogState === "applying";

  const description = isEnabled
    ? "Share crash reports and usage data with Imbue to help us improve the product."
    : "Crash reports and usage events are not being sent. Report a problem still works.";

  const handleOptIn = async (): Promise<void> => {
    // The switch is driven by the userConfig atom, which only updates once
    // the POST succeeds — disable it while the request is in flight so a
    // second click can't fire a concurrent, contradictory flip.
    setIsOptingIn(true);

    // Reconcile SDK state before the round-trip so any in-flight requests
    // ride the new consent. PostHog persists its distinct_id across
    // opt_out/opt_in cycles, so we don't need to re-identify the user
    // here — the identification done at app startup remains valid.
    applyTelemetryConsent(true, userEmail);

    try {
      const { data } = await setTelemetry({ body: { enabled: true }, meta: { skipWsAck: true } });
      if (data) {
        setUserConfig(data);
      }
      // Meta-event fires AFTER the POST so a failed opt-in doesn't leave a
      // misleading "opted_in" event in PostHog for a flip that didn't persist.
      posthog.capture("telemetry_opted_in");
    } catch (error) {
      console.error("set_telemetry POST failed during opt-in:", error);
      applyTelemetryConsent(false, userEmail);
      setToast({
        type: ToastType.ERROR_PROMINENT,
        title: "Couldn't enable telemetry",
        description: "Please try again.",
      });
    } finally {
      setIsOptingIn(false);
    }
  };

  const handleSwitchClick = (): void => {
    if (isEnabled) {
      setDialogState("open");
    } else {
      void handleOptIn();
    }
  };

  const handleConfirmOptOut = async (): Promise<void> => {
    setDialogState("applying");
    // Meta-event MUST fire before the opt-out flip — once we've opted out,
    // PostHog drops everything including this event.
    posthog.capture("telemetry_opted_out");
    applyTelemetryConsent(false, userEmail);
    try {
      const { data } = await setTelemetry({ body: { enabled: false }, meta: { skipWsAck: true } });
      if (data) {
        setUserConfig(data);
      }
      setDialogState("closed");
    } catch (error) {
      console.error("set_telemetry POST failed during opt-out:", error);
      applyTelemetryConsent(true, userEmail);
      setDialogState("closed");
      setToast({
        type: ToastType.ERROR_PROMINENT,
        title: "Couldn't disable telemetry",
        description: "Please try again.",
      });
    }
  };

  return (
    <>
      <SettingRow title="Telemetry" description={description} data-testid={ElementIds.SETTINGS_PRIVACY_TELEMETRY_ROW}>
        <Switch
          checked={isEnabled}
          disabled={isOptingIn}
          onCheckedChange={handleSwitchClick}
          data-testid={ElementIds.SETTINGS_PRIVACY_TELEMETRY_SWITCH}
        />
      </SettingRow>

      <AlertDialog.Root
        open={isDialogOpen}
        onOpenChange={(open) => {
          // Ignore outside-click / Escape close attempts while the POST is in
          // flight — the dialog's primary button drives the transition.
          if (!isApplying) setDialogState(open ? "open" : "closed");
        }}
      >
        <AlertDialog.Content maxWidth="440px" data-testid={ElementIds.SETTINGS_PRIVACY_TELEMETRY_DIALOG}>
          <AlertDialog.Title>Turn telemetry off?</AlertDialog.Title>
          <AlertDialog.Description>
            Crash reports and usage events will stop flowing from this machine. You can turn it back on at any time.
            Reports you send via &ldquo;Report a problem&rdquo; are still delivered.
          </AlertDialog.Description>
          <Flex gap="3" mt="4" justify="end">
            <AlertDialog.Cancel>
              <Button
                variant="soft"
                color="gray"
                disabled={isApplying}
                data-testid={ElementIds.SETTINGS_PRIVACY_TELEMETRY_DIALOG_CANCEL}
              >
                Cancel
              </Button>
            </AlertDialog.Cancel>
            <AlertDialog.Action>
              <Button
                variant="solid"
                onClick={handleConfirmOptOut}
                disabled={isApplying}
                aria-busy={isApplying}
                data-testid={ElementIds.SETTINGS_PRIVACY_TELEMETRY_DIALOG_CONFIRM}
              >
                {isApplying ? (
                  <Flex align="center" gap="2">
                    <Spinner size="1" />
                    Disabling Telemetry…
                  </Flex>
                ) : (
                  "Disable Telemetry"
                )}
              </Button>
            </AlertDialog.Action>
          </Flex>
        </AlertDialog.Content>
      </AlertDialog.Root>
    </>
  );
};
