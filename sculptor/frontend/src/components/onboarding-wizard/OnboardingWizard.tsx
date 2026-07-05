import { Flex } from "@radix-ui/themes";
import { posthog } from "posthog-js";
import type { ReactElement } from "react";
import { useState } from "react";

import { completeOnboarding, getConfigStatus, saveUserEmail, skipAccountSetup } from "~/api";
import { HTTPException } from "~/common/Errors.ts";
import { ValidationError } from "~/common/Errors.ts";
import { identifyAnalyticsUser, updateTelemetryConfig } from "~/common/Telemetry";
import { TitleBar } from "~/components/TitleBar";

import { AddRepoStep } from "./AddRepoStep.tsx";
import { InstallationStep } from "./InstallationStep.tsx";
import styles from "./OnboardingWizard.module.scss";
import { StepIndicator } from "./StepIndicator.tsx";
import { WelcomeStep } from "./WelcomeStep.tsx";

// eslint-disable-next-line react-refresh/only-export-components -- enum-style const shared with non-component code
export const OnboardingStep = {
  EMAIL: "EMAIL",
  INSTALLATION: "INSTALLATION",
  ADD_REPO: "ADD_REPO",
} as const;

export type OnboardingStep = (typeof OnboardingStep)[keyof typeof OnboardingStep];

const STEP_ORDER: ReadonlyArray<OnboardingStep> = [
  OnboardingStep.EMAIL,
  OnboardingStep.INSTALLATION,
  OnboardingStep.ADD_REPO,
];
const STEP_COUNT = STEP_ORDER.length;

type OnboardingWizardProps = {
  initialStep: OnboardingStep;
  onComplete: () => void;
};

export const OnboardingWizard = ({ initialStep, onComplete }: OnboardingWizardProps): ReactElement => {
  const [currentStep, setCurrentStep] = useState<OnboardingStep>(initialStep);
  const [maxVisitedStep, setMaxVisitedStep] = useState(STEP_ORDER.indexOf(initialStep));
  const [isLoading, setIsLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState<string | null>(null);
  const [didOptInToMarketing, setDidOptInToMarketing] = useState(false);
  const [isTelemetryEnabled, setIsTelemetryEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const goToStep = (step: OnboardingStep): void => {
    setCurrentStep(step);
    setMaxVisitedStep((prev) => Math.max(prev, STEP_ORDER.indexOf(step)));
    setError(null);
  };

  const handleEmailSubmit = async (
    email: string,
    fullName: string | null,
    didOptInToMarketing: boolean,
    isTelemetryEnabled: boolean,
  ): Promise<void> => {
    setIsLoading(true);
    setError(null);

    try {
      // Console output ends up in Sentry breadcrumbs (and potentially in
      // diagnostics), so never log the actual email/name.
      console.log("Saving user email. Marketing opt-in:", didOptInToMarketing);
      const { data: updatedTelemetryInfo } = await saveUserEmail({
        body: {
          userEmail: email,
          fullName: fullName,
          didOptInToMarketing: didOptInToMarketing,
          isTelemetryEnabled: isTelemetryEnabled,
        },
        meta: { skipWsAck: true },
      });
      if (updatedTelemetryInfo) {
        // Reconciles the SDKs with the chosen consent (opts PostHog in/out,
        // gates Sentry), so the calls below are no-ops when opted out.
        updateTelemetryConfig(updatedTelemetryInfo);
      }

      // Identify the user in PostHog and fire the email-confirmation event.
      // The Clay webhook subscribes to this event for mailing-list signup.
      // The frontend owns PostHog identification.
      if (isTelemetryEnabled) {
        identifyAnalyticsUser(email, fullName ? { full_name: fullName } : {});
        posthog.capture("onboarding.email_confirmation", {
          did_opt_in_to_marketing: didOptInToMarketing,
        });
      }

      setEmail(email);
      setFullName(fullName);
      setDidOptInToMarketing(didOptInToMarketing);
      setIsTelemetryEnabled(isTelemetryEnabled);
      goToStep(OnboardingStep.INSTALLATION);
    } catch (err) {
      let errorMessage = "Failed to save email";
      if (err instanceof ValidationError) {
        errorMessage = err.detail[0].msg;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSkipAccountSetup = async (isTelemetryEnabled: boolean): Promise<void> => {
    setIsLoading(true);
    setError(null);

    try {
      const { data: updatedTelemetryInfo } = await skipAccountSetup({
        body: { isTelemetryEnabled: isTelemetryEnabled },
        meta: { skipWsAck: true },
      });
      if (updatedTelemetryInfo) {
        updateTelemetryConfig(updatedTelemetryInfo);
      }

      // No identify and no email-confirmation event: without an account the
      // user stays anonymous in PostHog (random distinct_id only).
      setIsTelemetryEnabled(isTelemetryEnabled);
      goToStep(OnboardingStep.INSTALLATION);
    } catch (err) {
      let errorMessage = "Failed to continue without an account";
      if (err instanceof HTTPException) {
        errorMessage = err.detail;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInstallationComplete = async (): Promise<void> => {
    setIsLoading(true);
    setError(null);

    try {
      // Check if user already has a project — returning users should skip the add-repo step.
      const { data: configStatus } = await getConfigStatus({ meta: { skipWsAck: true } });
      if (configStatus?.hasProject) {
        await completeOnboarding({ meta: { skipWsAck: true } });
        onComplete();
        return;
      }

      goToStep(OnboardingStep.ADD_REPO);
    } catch (err) {
      let errorMessage = "Failed to check configuration";
      if (err instanceof HTTPException) {
        errorMessage = err.detail;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddRepoComplete = async (): Promise<void> => {
    setIsLoading(true);
    setError(null);

    try {
      await completeOnboarding({
        meta: { skipWsAck: true },
      });

      onComplete();
    } catch (err) {
      let errorMessage = "Failed to complete onboarding";
      if (err instanceof HTTPException) {
        errorMessage = err.detail;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStepClick = (index: number): void => {
    goToStep(STEP_ORDER[index]);
  };

  const currentStepIndex = STEP_ORDER.indexOf(currentStep);

  const renderStep = (): ReactElement => {
    if (currentStep === OnboardingStep.EMAIL) {
      return (
        <WelcomeStep
          onNext={handleEmailSubmit}
          onSkip={handleSkipAccountSetup}
          isLoading={isLoading}
          error={error}
          initialEmail={email}
          initialFullName={fullName}
          initialDidOptInToMarketing={didOptInToMarketing}
          initialIsTelemetryEnabled={isTelemetryEnabled}
        />
      );
    }

    if (currentStep === OnboardingStep.INSTALLATION) {
      return <InstallationStep onComplete={handleInstallationComplete} isLoading={isLoading} error={error} />;
    }

    return <AddRepoStep onComplete={handleAddRepoComplete} isLoading={isLoading} error={error} />;
  };

  return (
    <Flex direction="column" className={styles.wizardContainer}>
      <TitleBar />
      <StepIndicator
        totalSteps={STEP_COUNT}
        currentStep={currentStepIndex}
        maxVisitedStep={maxVisitedStep}
        onStepClick={handleStepClick}
      />
      <Flex direction="column" className={styles.contentArea}>
        <div className={styles.stepContent}>{renderStep()}</div>
      </Flex>
    </Flex>
  );
};
