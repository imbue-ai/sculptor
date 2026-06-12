import { Text, Tooltip } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChevronDown, GitBranchIcon, GitMergeIcon, PlusIcon } from "lucide-react";
import type { ReactElement } from "react";

import prStyles from "~/pages/workspace/components/PrButton.module.scss";
import { TargetBranchSelector } from "~/pages/workspace/components/TargetBranchSelector";
import bannerStyles from "~/pages/workspace/components/WorkspaceBanner.module.scss";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const REMOTE_BRANCHES = ["origin/main", "origin/develop", "origin/release/v2"];

const handleBranchChange = (branch: string): void => {
  console.log("Target branch changed:", branch);
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type MrState = "none" | "open" | "loading";

type StoryProps = {
  currentBranch: string;
  targetBranch: string;
  gitProvider: "gitlab" | "github";
  mrState: MrState;
  /** Whether an MR exists on a different target branch */
  hasMismatchedMr: boolean;
  /** The MR iid of the mismatched MR */
  mismatchedMrIid: number;
  /** The branch the mismatched MR actually targets */
  mismatchedMrTarget: string;
};

// ---------------------------------------------------------------------------
// "Assign MR" button (single button, no dropdown)
// ---------------------------------------------------------------------------

// Static mock of AssignPrButton from PrButton.tsx — the real component uses
// Jotai atoms and chat actions that aren't available in Storybook. If the real
// component's UI changes, this mock needs to be updated to match.
const AssignMrButton = ({ gitProvider }: { gitProvider: "gitlab" | "github" }): ReactElement => {
  const isGitLab = gitProvider === "gitlab";
  const assignLabel = isGitLab ? "Assign MR" : "Assign PR";

  return (
    <div className={prStyles.assignButton}>
      <span
        role="button"
        tabIndex={0}
        className={prStyles.assignMainArea}
        onClick={() => console.log("Assign MR clicked")}
      >
        <GitMergeIcon size={12} className={prStyles.assignMergeIcon} />
        <Text size="1">{assignLabel}</Text>
      </span>
    </div>
  );
};

// ---------------------------------------------------------------------------
// SVG helpers
// ---------------------------------------------------------------------------

const ChevronDownIcon = (): ReactElement => <ChevronDown size={12} />;

// ---------------------------------------------------------------------------
// Diff summary placeholder
// ---------------------------------------------------------------------------

const DiffSummaryMock = (): ReactElement => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, flexShrink: 0 }}>
    <span style={{ color: "var(--green-9)" }}>+42</span>
    <span style={{ color: "var(--red-9)" }}>-8</span>
  </span>
);

// ---------------------------------------------------------------------------
// Banner shell
// ---------------------------------------------------------------------------

const BannerShell = ({
  currentBranch,
  targetBranch,
  gitProvider,
  mrState,
  hasMismatchedMr,
  mismatchedMrIid,
  mismatchedMrTarget,
}: StoryProps): ReactElement => {
  const isGitLab = gitProvider === "gitlab";
  const prefix = isGitLab ? "!" : "#";
  const label = isGitLab ? "MR" : "PR";
  const createLabel = isGitLab ? "Create MR" : "Create PR";
  const isMismatch = hasMismatchedMr && mrState === "none";

  const tooltipContent = isMismatch
    ? `Retarget to origin/${mismatchedMrTarget} — ${label} ${prefix}${mismatchedMrIid} targets this branch`
    : "Target branch";

  return (
    <div style={{ width: 900 }}>
      <div className={bannerStyles.banner} style={{ overflow: "visible" }}>
        {/* Branch name */}
        <Tooltip content="Workspace branch" side="bottom">
          <span className={bannerStyles.branchSection}>
            <GitBranchIcon size={12} className={bannerStyles.branchIcon} />
            <span className={bannerStyles.branchName}>{currentBranch}</span>
          </span>
        </Tooltip>

        {/* Arrow */}
        <span className={bannerStyles.arrowSeparator}>&rarr;</span>

        {/* Target branch selector — amber when mismatched, with badge in dropdown */}
        <Tooltip content={tooltipContent} side="bottom">
          <span>
            <TargetBranchSelector
              currentTargetBranch={targetBranch}
              remoteBranches={REMOTE_BRANCHES}
              onBranchChange={handleBranchChange}
              variant={isMismatch ? "amber" : "default"}
              mismatch={
                isMismatch
                  ? {
                      targetBranch: mismatchedMrTarget,
                      badge: {
                        text: `${label} ${prefix}${mismatchedMrIid}`,
                        tooltip: `Open ${label} targets this branch`,
                      },
                    }
                  : null
              }
            />
          </span>
        </Tooltip>

        {/* Spacer */}
        <div className={bannerStyles.spacer} />

        <DiffSummaryMock />

        {/* PR Button area */}
        {isMismatch ? (
          <AssignMrButton gitProvider={gitProvider} />
        ) : (
          <>
            {mrState === "none" && (
              <div className={prStyles.createSplitButton}>
                <span role="button" tabIndex={0} className={prStyles.createMainArea}>
                  <PlusIcon size={12} className={prStyles.plusIcon} />
                  <Text size="1">{createLabel}</Text>
                </span>
                <span className={prStyles.createChevronArea}>
                  <ChevronDownIcon />
                </span>
              </div>
            )}

            {mrState === "open" && (
              <div className={prStyles.openButton}>
                <span role="button" tabIndex={0} className={prStyles.prNumberArea}>
                  <Text size="1">
                    {label} {prefix}847
                  </Text>
                  <span className={`${prStyles.statusDot} ${prStyles.dotPassed}`} />
                  <span className={`${prStyles.statusDot} ${prStyles.dotPending}`} />
                </span>
                <span className={prStyles.chevronArea}>
                  <ChevronDownIcon />
                </span>
              </div>
            )}

            {mrState === "loading" && (
              <div className={prStyles.loadingButton}>
                <Text size="1">Checking {label}...</Text>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

const meta = {
  title: "Custom/WorkspaceBanner",
  component: BannerShell,
  args: {
    currentBranch: "dev/fix/auth-flow",
    targetBranch: "origin/develop",
    gitProvider: "gitlab",
    mrState: "none",
    hasMismatchedMr: false,
    mismatchedMrIid: 847,
    mismatchedMrTarget: "main",
  },
  argTypes: {
    mrState: {
      control: "select",
      options: ["none", "open", "loading"],
    },
    gitProvider: {
      control: "select",
      options: ["gitlab", "github"],
    },
  },
  parameters: {
    layout: "padded",
  },
} satisfies Meta<typeof BannerShell>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

/** Normal state — no MR exists, target matches intent. */
export const CreateMr: Story = {
  args: {
    mrState: "none",
    hasMismatchedMr: false,
  },
};

/** An open MR exists and the target matches the workspace target. */
export const OpenMr: Story = {
  args: {
    targetBranch: "origin/main",
    mrState: "open",
    hasMismatchedMr: false,
  },
};

/** MR exists on different target — amber target branch + "Assign MR" button. */
export const MismatchedMrResting: Story = {
  args: {
    targetBranch: "origin/develop",
    mrState: "none",
    hasMismatchedMr: true,
    mismatchedMrIid: 847,
    mismatchedMrTarget: "main",
  },
};

/** GitHub variant — amber target + "Assign PR". */
export const MismatchedPrGitHub: Story = {
  args: {
    targetBranch: "origin/develop",
    gitProvider: "github",
    mrState: "none",
    hasMismatchedMr: true,
    mismatchedMrIid: 312,
    mismatchedMrTarget: "main",
  },
};

/** Loading state while checking MR status. */
export const Loading: Story = {
  args: {
    mrState: "loading",
    hasMismatchedMr: false,
  },
};
