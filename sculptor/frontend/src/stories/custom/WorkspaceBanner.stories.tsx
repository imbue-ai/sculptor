import { Text, Tooltip } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChevronDown, GitBranchIcon, GitMergeIcon, PlusIcon } from "lucide-react";
import type { ReactElement } from "react";

import prStyles from "~/pages/workspace/components/PrButton.module.scss";
import { TargetBranchSelector } from "~/pages/workspace/components/TargetBranchSelector";
import bannerStyles from "~/pages/workspace/components/WorkspaceBanner.module.scss";

const REMOTE_BRANCHES = ["origin/main", "origin/develop", "origin/release/v2"];

const handleBranchChange = (branch: string): void => {
  console.log("Target branch changed:", branch);
};

type PrState = "none" | "open" | "loading";

type StoryProps = {
  currentBranch: string;
  targetBranch: string;
  prState: PrState;
  /** Whether a PR exists on a different target branch */
  hasMismatchedPr: boolean;
  /** The number of the mismatched PR */
  mismatchedPrNumber: number;
  /** The branch the mismatched PR actually targets */
  mismatchedPrTarget: string;
};

// Static mock of AssignPrButton from PrButton.tsx — the real component uses
// Jotai atoms and chat actions that aren't available in Storybook. If the real
// component's UI changes, this mock needs to be updated to match.
const AssignPrButton = (): ReactElement => {
  return (
    <div className={prStyles.assignButton}>
      <span
        role="button"
        tabIndex={0}
        className={prStyles.assignMainArea}
        onClick={() => console.log("Assign PR clicked")}
      >
        <GitMergeIcon size={12} className={prStyles.assignMergeIcon} />
        <Text size="1">Assign PR</Text>
      </span>
    </div>
  );
};

const ChevronDownIcon = (): ReactElement => <ChevronDown size={12} />;

const DiffSummaryMock = (): ReactElement => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, flexShrink: 0 }}>
    <span style={{ color: "var(--green-9)" }}>+42</span>
    <span style={{ color: "var(--red-9)" }}>-8</span>
  </span>
);

const BannerShell = ({
  currentBranch,
  targetBranch,
  prState,
  hasMismatchedPr,
  mismatchedPrNumber,
  mismatchedPrTarget,
}: StoryProps): ReactElement => {
  const isMismatch = hasMismatchedPr && prState === "none";

  const tooltipContent = isMismatch
    ? `Retarget to origin/${mismatchedPrTarget} — PR #${mismatchedPrNumber} targets this branch`
    : "Target branch";

  return (
    <div style={{ width: 900 }}>
      <div className={bannerStyles.banner} style={{ overflow: "visible" }}>
        <Tooltip content="Workspace branch" side="bottom">
          <span className={bannerStyles.branchSection}>
            <GitBranchIcon size={12} className={bannerStyles.branchIcon} />
            <span className={bannerStyles.branchName}>{currentBranch}</span>
          </span>
        </Tooltip>

        <span className={bannerStyles.arrowSeparator}>&rarr;</span>

        <Tooltip content={tooltipContent} side="bottom">
          <span>
            <TargetBranchSelector
              currentTargetBranch={targetBranch}
              targetBranches={REMOTE_BRANCHES}
              onBranchChange={handleBranchChange}
              variant={isMismatch ? "amber" : "default"}
              mismatch={
                isMismatch
                  ? {
                      targetBranch: mismatchedPrTarget,
                      badge: {
                        text: `PR #${mismatchedPrNumber}`,
                        tooltip: `Open PR targets this branch`,
                      },
                    }
                  : undefined
              }
            />
          </span>
        </Tooltip>

        <div className={bannerStyles.spacer} />

        <DiffSummaryMock />

        {isMismatch ? (
          <AssignPrButton />
        ) : (
          <>
            {prState === "none" && (
              <div className={prStyles.createSplitButton}>
                <span role="button" tabIndex={0} className={prStyles.createMainArea}>
                  <PlusIcon size={12} className={prStyles.plusIcon} />
                  <Text size="1">Create PR</Text>
                </span>
                <span className={prStyles.createChevronArea}>
                  <ChevronDownIcon />
                </span>
              </div>
            )}

            {prState === "open" && (
              <div className={prStyles.openButton}>
                <span role="button" tabIndex={0} className={prStyles.prNumberArea}>
                  <Text size="1">PR #847</Text>
                  <span className={`${prStyles.statusDot} ${prStyles.dotPassed}`} />
                  <span className={`${prStyles.statusDot} ${prStyles.dotPending}`} />
                </span>
                <span className={prStyles.chevronArea}>
                  <ChevronDownIcon />
                </span>
              </div>
            )}

            {prState === "loading" && (
              <div className={prStyles.loadingButton}>
                <Text size="1">Checking PR...</Text>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

const meta = {
  title: "Custom/WorkspaceBanner",
  component: BannerShell,
  args: {
    currentBranch: "dev/fix/auth-flow",
    targetBranch: "origin/develop",
    prState: "none",
    hasMismatchedPr: false,
    mismatchedPrNumber: 847,
    mismatchedPrTarget: "main",
  },
  argTypes: {
    prState: {
      control: "select",
      options: ["none", "open", "loading"],
    },
  },
  parameters: {
    layout: "padded",
  },
} satisfies Meta<typeof BannerShell>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

/** Normal state — no PR exists, target matches intent. */
export const CreatePr: Story = {
  args: {
    prState: "none",
    hasMismatchedPr: false,
  },
};

/** An open PR exists and the target matches the workspace target. */
export const OpenPr: Story = {
  args: {
    targetBranch: "origin/main",
    prState: "open",
    hasMismatchedPr: false,
  },
};

/** PR exists on different target — amber target branch + "Assign PR" button. */
export const MismatchedPr: Story = {
  args: {
    targetBranch: "origin/develop",
    prState: "none",
    hasMismatchedPr: true,
    mismatchedPrNumber: 312,
    mismatchedPrTarget: "main",
  },
};

/** Loading state while checking PR status. */
export const Loading: Story = {
  args: {
    prState: "loading",
    hasMismatchedPr: false,
  },
};
