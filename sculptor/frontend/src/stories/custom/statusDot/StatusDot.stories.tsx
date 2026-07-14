import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChevronDown, Command, Home, Plus } from "lucide-react";
import type { ReactElement } from "react";

import { NavItem } from "~/components/nav/NavItem.tsx";
import groupStyles from "~/components/nav/SidebarRepoGroup.module.scss";
import sidebarStyles from "~/components/nav/WorkspaceSidebar.module.scss";
import {
  AgentStatusDot,
  type AgentDotStatus,
  WorkspaceStatusDots,
  type WorkspaceDotStatus,
} from "~/components/statusDot";

/**
 * Visual reference for the status glyphs and the sidebar rail treatment.
 *
 * The glyph rows render the real AgentStatusDot / WorkspaceStatusDots. The rail
 * preview composes the real sidebar CSS modules and the real NavItem with static
 * rows (the live SidebarRepoGroup is atom-driven), so the recolor, type
 * hierarchy, and status glyphs can be screenshotted together without a running
 * backend. Every running blob self-seeds, so a column of them animates out of
 * sync — which is the point of viewing several at once here.
 */

const AGENT_STATES: ReadonlyArray<{ status: AgentDotStatus; label: string }> = [
  { status: "running", label: "Running" },
  { status: "waiting", label: "Waiting" },
  { status: "error", label: "Error" },
  { status: "unread", label: "Ready (unread)" },
  { status: "read", label: "Idle (read)" },
];

const emptyStatus: WorkspaceDotStatus = {
  hasError: false,
  hasWaiting: false,
  hasRunning: false,
  isAllError: false,
  hasUnread: false,
};

const WORKSPACE_STATES: ReadonlyArray<{ status: WorkspaceDotStatus; label: string }> = [
  { status: { ...emptyStatus, hasRunning: true }, label: "Running" },
  { status: { ...emptyStatus, hasWaiting: true }, label: "Waiting" },
  { status: { ...emptyStatus, hasUnread: true }, label: "Ready" },
  { status: { ...emptyStatus, hasError: true, isAllError: true }, label: "All error" },
  { status: { ...emptyStatus, hasError: true, hasRunning: true }, label: "Error + running" },
  { status: emptyStatus, label: "Idle" },
];

const StatusRow = ({ label, children }: { label: string; children: ReactElement }): ReactElement => (
  <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
    <span style={{ width: "140px", fontSize: "13px", color: "var(--gray-11)" }}>{label}</span>
    {children}
  </div>
);

const GlyphGallery = (): ReactElement => (
  <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--gray-12)" }}>Agent status</span>
      {AGENT_STATES.map(({ status, label }) => (
        <StatusRow key={status} label={label}>
          <AgentStatusDot status={status} />
        </StatusRow>
      ))}
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--gray-12)" }}>Workspace aggregate</span>
      {WORKSPACE_STATES.map(({ status, label }) => (
        <StatusRow key={label} label={label}>
          <WorkspaceStatusDots status={status} />
        </StatusRow>
      ))}
    </div>
  </div>
);

/** A static workspace row using the real repo-group classes. */
const RailWorkspaceRow = ({
  name,
  status,
  isActive = false,
}: {
  name: string;
  status: WorkspaceDotStatus;
  isActive?: boolean;
}): ReactElement => (
  <div className={`${groupStyles.workspaceRow} ${isActive ? groupStyles.workspaceRowActive : ""}`}>
    <span className={groupStyles.workspaceRowButton}>
      <span className={groupStyles.workspaceDot}>
        <WorkspaceStatusDots status={status} />
      </span>
      <span className={groupStyles.workspaceName}>{name}</span>
    </span>
  </div>
);

/** A static repo group (header + rows) using the real repo-group classes. */
const RailRepoGroup = ({
  name,
  children,
}: {
  name: string;
  children: ReactElement | ReactElement[];
}): ReactElement => (
  <div className={groupStyles.repoGroup}>
    <div className={groupStyles.repoHeader}>
      <span className={groupStyles.repoHeaderButton}>
        <ChevronDown size={16} className={groupStyles.repoChevron} />
        <span className={groupStyles.repoName}>{name}</span>
      </span>
    </div>
    <div className={groupStyles.repoRows}>{children}</div>
  </div>
);

const running: WorkspaceDotStatus = { ...emptyStatus, hasRunning: true };

const SidebarRailPreview = (): ReactElement => (
  <aside className={sidebarStyles.sidebar} style={{ width: "264px", height: "560px" }}>
    <nav className={sidebarStyles.topActions}>
      <NavItem icon={Home} label="Home" isActive onClick={() => {}} />
      <NavItem icon={Command} label="Commands" onClick={() => {}} />
      <NavItem icon={Plus} label="New Workspace" onClick={() => {}} />
    </nav>
    <div className={sidebarStyles.repoList}>
      <RailRepoGroup name="sculptor">
        {/* Several running rows so the self-seeded blobs visibly drift apart. */}
        <RailWorkspaceRow name="fix-auth-flow" status={running} isActive />
        <RailWorkspaceRow name="rebuild-search-index" status={running} />
        <RailWorkspaceRow name="add-dashboard-panel" status={{ ...emptyStatus, hasWaiting: true }} />
        <RailWorkspaceRow name="refactor-parser" status={{ ...emptyStatus, hasUnread: true }} />
        <RailWorkspaceRow name="flaky-integration-test" status={{ ...emptyStatus, hasError: true, isAllError: true }} />
      </RailRepoGroup>
      <RailRepoGroup name="marketing-site">
        <RailWorkspaceRow name="hero-redesign" status={running} />
        <RailWorkspaceRow name="pricing-copy" status={emptyStatus} />
      </RailRepoGroup>
    </div>
  </aside>
);

const Showcase = (): ReactElement => (
  <div style={{ display: "flex", gap: "48px", alignItems: "flex-start", padding: "8px" }}>
    <SidebarRailPreview />
    <GlyphGallery />
  </div>
);

const meta = {
  title: "Custom/StatusDot",
  parameters: { layout: "centered" },
} satisfies Meta;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Glyphs: Story = {
  render: (): ReactElement => <GlyphGallery />,
};

export const SidebarRail: Story = {
  render: (): ReactElement => <SidebarRailPreview />,
};

export const Showcase_: Story = {
  name: "Showcase",
  render: (): ReactElement => <Showcase />,
};
