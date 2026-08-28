import type React from "react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./StepIndicator.module.scss";

type StepIndicatorProps = {
  totalSteps: number;
  currentStep: number;
  maxVisitedStep?: number;
  onStepClick?: (step: number) => void;
};

export const StepIndicator = ({
  totalSteps,
  currentStep,
  maxVisitedStep,
  onStepClick,
}: StepIndicatorProps): ReactElement => {
  const visited = maxVisitedStep ?? currentStep;

  return (
    <div className={styles.container}>
      {Array.from({ length: totalSteps }, (_, i) => {
        const isCurrent = i === currentStep;
        const isClickable = i !== currentStep && i <= visited && onStepClick !== undefined;

        return (
          <span
            key={i}
            role="button"
            tabIndex={isClickable ? 0 : -1}
            data-testid={ElementIds.ONBOARDING_STEP_INDICATOR_DOT}
            data-step={i}
            className={`${styles.dot} ${isCurrent ? styles.current : ""} ${i <= visited ? styles.visited : styles.upcoming} ${isClickable ? styles.clickable : ""}`}
            onClick={isClickable ? (): void => onStepClick(i) : undefined}
            onKeyDown={
              isClickable
                ? (e: React.KeyboardEvent): void => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onStepClick(i);
                    }
                  }
                : undefined
            }
            aria-label={`Go to step ${i + 1}`}
            aria-disabled={!isClickable}
          />
        );
      })}
    </div>
  );
};
