import { Spinner } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";
import { useEffect, useState } from "react";

import { getConfigStatus } from "../api";
import { OnboardingStep, OnboardingWizard } from "./onboarding-wizard";

type RequireOnboardingProps = {
  children: ReactNode;
};

export const RequireOnboarding = ({ children }: RequireOnboardingProps): ReactElement => {
  const [isCheckingConfig, setIsCheckingConfig] = useState(true);
  const [isOnboardingComplete, setIsOnboardingComplete] = useState(false);
  const [currentOnboardingStep, setCurrentOnboardingStep] = useState<OnboardingStep>(OnboardingStep.EMAIL);

  // Check config status to determine if onboarding is needed
  useEffect(() => {
    const checkConfigStatus = async (): Promise<void> => {
      try {
        const { data: configStatus } = await getConfigStatus({
          meta: { skipWsAck: true },
        });

        // Privacy consent marks the welcome step as completed — an email is
        // optional (the user can continue without an account and stay
        // anonymous).
        const hasUserConfig = configStatus.hasPrivacyConsent;
        const isComplete = hasUserConfig && configStatus.hasDependenciesPassing && configStatus.hasProject;

        if (isComplete) {
          setIsOnboardingComplete(true);
        } else if (!hasUserConfig) {
          // New user: start from the beginning. A legacy user with an email
          // but no recorded consent resumes at installation; completing
          // onboarding backfills the consent.
          setCurrentOnboardingStep(configStatus.hasEmail ? OnboardingStep.INSTALLATION : OnboardingStep.EMAIL);
          setIsOnboardingComplete(false);
        } else if (!configStatus.hasProject) {
          // Returning user: config exists but no project (e.g. deleted last repo).
          setCurrentOnboardingStep(OnboardingStep.ADD_REPO);
          setIsOnboardingComplete(false);
        } else {
          // Returning user: config exists but deps aren't passing.
          setCurrentOnboardingStep(OnboardingStep.INSTALLATION);
          setIsOnboardingComplete(false);
        }
      } catch (error) {
        console.error("Failed to check config status:", error);
        // If config check fails, assume onboarding is needed
        setIsOnboardingComplete(false);
        setCurrentOnboardingStep(OnboardingStep.EMAIL);
      }
      setIsCheckingConfig(false);
    };

    checkConfigStatus();
  }, []);

  const handleOnboardingComplete = (): void => {
    setIsOnboardingComplete(true);
  };

  if (isCheckingConfig) {
    return <Spinner />;
  }

  if (!isOnboardingComplete) {
    return <OnboardingWizard initialStep={currentOnboardingStep} onComplete={handleOnboardingComplete} />;
  }

  return <>{children}</>;
};
