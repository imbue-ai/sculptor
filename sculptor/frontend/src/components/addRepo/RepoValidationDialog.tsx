import { Dialog } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { AddRepoPhase } from "~/components/addRepo/hooks/useAddRepo.tsx";

import styles from "./RepoValidationDialog.module.scss";
import { RepoValidationView } from "./RepoValidationView.tsx";

type RepoValidationDialogProps = {
  isOpen: boolean;
  phase: Exclude<AddRepoPhase, { type: "form" | "validating" | "cloning" }>;
  onInitializeGit: () => void;
  onCreateInitialCommit: () => void;
  onCancel: () => void;
  /** Triggered by the "Add as local folder" CTA in the clone-failed phase. */
  onOpenLocal?: (path: string) => void;
};

/**
 * Wraps {@link RepoValidationView} in its own Radix Dialog for callers that
 * render the validation flow on top of a non-dialog page (e.g. the onboarding
 * wizard). When the validation flow is shown inside a parent dialog, use
 * {@link RepoValidationView} directly to avoid stacking two dialogs.
 *
 * The Content node carries `styles.transparentOverlay` so the SCSS module can
 * neutralize the Radix overlay's `::before` background for this dialog only,
 * keeping the underlying page visible behind it.
 */
export const RepoValidationDialog = ({
  isOpen,
  phase,
  onInitializeGit,
  onCreateInitialCommit,
  onCancel,
  onOpenLocal,
}: RepoValidationDialogProps): ReactElement => {
  return (
    <Dialog.Root open={isOpen}>
      <Dialog.Content className={styles.transparentOverlay} maxWidth="420px">
        <RepoValidationView
          phase={phase}
          onInitializeGit={onInitializeGit}
          onCreateInitialCommit={onCreateInitialCommit}
          onCancel={onCancel}
          onOpenLocal={onOpenLocal}
        />
      </Dialog.Content>
    </Dialog.Root>
  );
};
