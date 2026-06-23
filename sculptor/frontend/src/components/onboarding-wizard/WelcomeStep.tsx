import { Button, Checkbox, Flex, Link, Spinner, Text, TextField } from "@radix-ui/themes";
import type React from "react";
import type { ReactElement } from "react";
import { useState } from "react";

import { ElementIds } from "~/api";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

import styles from "./OnboardingWizard.module.scss";

type WelcomeStepProps = {
  onNext: (email: string, fullName: string | null, didOptInToMarketing: boolean, isTelemetryEnabled: boolean) => void;
  onSkip: (isTelemetryEnabled: boolean) => void;
  isLoading: boolean;
  error: string | null;
  initialEmail: string;
  initialFullName: string | null;
  initialDidOptInToMarketing: boolean;
  initialIsTelemetryEnabled: boolean;
};

export const WelcomeStep = ({
  onNext,
  onSkip,
  isLoading,
  error,
  initialEmail,
  initialFullName,
  initialDidOptInToMarketing,
  initialIsTelemetryEnabled,
}: WelcomeStepProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const [email, setEmail] = useState(initialEmail);
  const [fullName, setFullName] = useState(initialFullName);
  const [didOptInToMarketing, setDidOptInToMarketing] = useState(initialDidOptInToMarketing);
  const [isTelemetryEnabled, setIsTelemetryEnabled] = useState(initialIsTelemetryEnabled);

  const handleSubmit = (): void => {
    if (email && email.includes("@")) {
      onNext(email, fullName || null, didOptInToMarketing, isTelemetryEnabled);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent): void => {
    if (e.key === "Enter") {
      handleSubmit();
    }
  };

  return (
    <Flex direction="column" data-testid={ElementIds.ONBOARDING_WELCOME_STEP}>
      <Text className={styles.titleText}>Start building with Sculptor</Text>
      <Flex className={styles.tosAndPrivacy} direction="column">
        <Text size="2" color="gray">
          Your code is yours — Imbue does not store your repositories or train on your code.
        </Text>
        <Text size="2" color="gray">
          We encourage you to also review the privacy rules of your model providers.
        </Text>
        <Text size="2" color="gray">
          By continuing, you agree to our{" "}
          <Link className={styles.termsText} href="https://imbue.com/terms">
            terms of service
          </Link>{" "}
          and{" "}
          <Link className={styles.termsText} href="https://imbue.com/privacy">
            privacy policy
          </Link>
          .
        </Text>
      </Flex>
      <Flex direction="column" mt="5" gap="3" width="100%">
        <TextField.Root
          placeholder="Full name"
          size="3"
          autoFocus
          value={fullName ?? ""}
          onChange={(e) => setFullName(e.target.value)}
          onKeyDown={handleKeyPress}
          className={styles.nameInput}
          data-testid={ElementIds.ONBOARDING_FULL_NAME_INPUT}
        />
        <TextField.Root
          placeholder="Email address"
          size="3"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={handleKeyPress}
          className={styles.emailInput}
          data-testid={ElementIds.ONBOARDING_EMAIL_INPUT}
        />
        {error && (
          <Text size="2" color={dangerColor} className={styles.error} data-testid={ElementIds.ONBOARDING_EMAIL_ERROR}>
            {error}
          </Text>
        )}
        <Button
          mt="1"
          size="3"
          variant="solid"
          onClick={handleSubmit}
          disabled={isLoading || !email || !email.includes("@")}
          className={styles.primaryButton}
          data-testid={ElementIds.ONBOARDING_EMAIL_SUBMIT}
        >
          {isLoading ? <Spinner /> : "Get Started"}
        </Button>
        <Flex direction="column" gap="2" mt="1">
          <Text as="label" size="2">
            <Flex gap="2" align="center">
              <Checkbox
                checked={didOptInToMarketing}
                onCheckedChange={(checked) => setDidOptInToMarketing(checked === true)}
                data-testid={ElementIds.ONBOARDING_MARKETING_CHECKBOX}
              />
              <Text size="2" color="gray">
                Receive product update emails
              </Text>
            </Flex>
          </Text>
          <Text as="label" size="2">
            <Flex gap="2" align="center">
              <Checkbox
                checked={isTelemetryEnabled}
                onCheckedChange={(checked) => setIsTelemetryEnabled(checked === true)}
                data-testid={ElementIds.ONBOARDING_TELEMETRY_CHECKBOX}
              />
              <Text size="2" color="gray">
                Share crash reports and usage data to help improve Sculptor
              </Text>
            </Flex>
          </Text>
        </Flex>
        <Button
          type="button"
          variant="ghost"
          size="2"
          className={styles.skipLink}
          // Reflect the in-flight gate in the DOM so assistive tech and
          // Playwright's actionability checks see the control as inert; the
          // onClick early-return stays as defense-in-depth. aria-disabled
          // (rather than disabled) keeps the control focusable and
          // discoverable to screen readers while a submit is pending.
          aria-disabled={isLoading}
          onClick={() => {
            if (!isLoading) {
              onSkip(isTelemetryEnabled);
            }
          }}
          data-testid={ElementIds.ONBOARDING_SKIP_ACCOUNT_LINK}
        >
          Continue without an account
        </Button>
      </Flex>
    </Flex>
  );
};
