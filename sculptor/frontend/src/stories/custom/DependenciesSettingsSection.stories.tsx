import type { Meta, StoryObj } from "@storybook/react-vite";
import { createStore, Provider as JotaiProvider } from "jotai";
import type { ReactElement } from "react";

import type { DependenciesStatus, DependencyInfo } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus";
import { DependenciesSettingsSection } from "~/pages/settings/components/DependenciesSettingsSection";

const piNotInstalled = {
  installed: false,
  path: null,
  version: null,
  isOverride: false,
  mode: null,
  versionRange: { minVersion: "0.82.0", maxVersion: "0.82.0", recommendedVersion: "0.82.0" },
  isVersionInRange: null,
} as const;

const optionalCliNotInstalled: DependencyInfo = {
  installed: false,
  path: null,
  version: null,
  isOverride: false,
  mode: null,
  versionRange: null,
  isVersionInRange: null,
};

const ghInstalled: DependencyInfo = {
  installed: true,
  path: "/opt/homebrew/bin/gh",
  version: "2.65.0",
  isOverride: false,
  mode: null,
  versionRange: null,
  isVersionInRange: null,
  isAuthenticated: true,
};

const ghInstalledNotAuthed: DependencyInfo = {
  installed: true,
  path: "/opt/homebrew/bin/gh",
  version: "2.65.0",
  isOverride: false,
  mode: null,
  versionRange: null,
  isVersionInRange: null,
  isAuthenticated: false,
};

const managedUpToDate: DependenciesStatus = {
  git: {
    installed: true,
    path: "/usr/bin/git",
    version: "2.43.0",
    isOverride: false,
    mode: null,
    versionRange: null,
    isVersionInRange: null,
  },
  claude: {
    installed: true,
    path: "/home/user/.sculptor/bin/claude",
    version: "1.0.16",
    isOverride: false,
    mode: "MANAGED",
    versionRange: { minVersion: "1.0.0", maxVersion: "2.0.0", recommendedVersion: "1.0.16" },
    isVersionInRange: true,
    managedVersion: "1.0.16",
  },
  pi: piNotInstalled,
  gh: optionalCliNotInstalled,
};

const managedOutOfRange: DependenciesStatus = {
  git: {
    installed: true,
    path: "/usr/bin/git",
    version: "2.43.0",
    isOverride: false,
    mode: null,
    versionRange: null,
    isVersionInRange: null,
  },
  claude: {
    installed: true,
    path: "/home/user/.sculptor/bin/claude",
    version: "0.9.2",
    isOverride: false,
    mode: "MANAGED",
    versionRange: { minVersion: "1.0.0", maxVersion: "2.0.0", recommendedVersion: "1.0.16" },
    isVersionInRange: false,
    managedVersion: "0.9.2",
  },
  pi: piNotInstalled,
  gh: optionalCliNotInstalled,
};

const pathMode: DependenciesStatus = {
  git: {
    installed: true,
    path: "/usr/bin/git",
    version: "2.43.0",
    isOverride: false,
    mode: null,
    versionRange: null,
    isVersionInRange: null,
  },
  claude: {
    installed: true,
    path: "/usr/local/bin/claude",
    version: "1.0.12",
    isOverride: false,
    mode: "CUSTOM",
    versionRange: { minVersion: "1.0.0", maxVersion: "2.0.0", recommendedVersion: "1.0.16" },
    isVersionInRange: true,
  },
  pi: piNotInstalled,
  gh: optionalCliNotInstalled,
};

const customMode: DependenciesStatus = {
  git: {
    installed: true,
    path: "/usr/bin/git",
    version: "2.43.0",
    isOverride: false,
    mode: null,
    versionRange: null,
    isVersionInRange: null,
  },
  claude: {
    installed: true,
    path: "/opt/claude/bin/claude",
    version: "1.0.10",
    isOverride: false,
    mode: "CUSTOM",
    versionRange: { minVersion: "1.0.0", maxVersion: "2.0.0", recommendedVersion: "1.0.16" },
    isVersionInRange: true,
  },
  pi: piNotInstalled,
  gh: optionalCliNotInstalled,
};

const notInstalled: DependenciesStatus = {
  git: {
    installed: false,
    path: null,
    version: null,
    isOverride: false,
    mode: null,
    versionRange: null,
    isVersionInRange: null,
  },
  claude: {
    installed: false,
    path: null,
    version: null,
    isOverride: false,
    mode: "MANAGED",
    versionRange: { minVersion: "1.0.0", maxVersion: "2.0.0", recommendedVersion: "1.0.16" },
    isVersionInRange: null,
  },
  pi: piNotInstalled,
  gh: optionalCliNotInstalled,
};

const withInstallProgress: DependenciesStatus = {
  ...managedOutOfRange,
  claude: {
    ...managedOutOfRange.claude,
    installProgress: {
      tool: "CLAUDE",
      bytesDownloaded: 45_000_000,
      totalBytes: 120_000_000,
    },
  },
};

// SCU-1271: a managed upgrade whose download failed. The new version never
// installed, so the service is still resolving the stale, out-of-range binary
// on disk; install_error now carries the reason so the UI can explain it
// instead of silently showing a bare "Out of range".
const managedUpgradeFailed: DependenciesStatus = {
  git: {
    installed: true,
    path: "/usr/bin/git",
    version: "2.43.0",
    isOverride: false,
    mode: null,
    versionRange: null,
    isVersionInRange: null,
  },
  claude: {
    installed: true,
    path: "/home/user/.sculptor/internal/dependencies/claude/version-2.1.111/claude",
    version: "2.1.111",
    isOverride: false,
    mode: "MANAGED",
    versionRange: { minVersion: "2.1.156", maxVersion: "2.99.99", recommendedVersion: "2.1.156" },
    isVersionInRange: false,
    managedVersion: "2.1.111",
    installError: "Download failed: Server error '503 Service Unavailable'",
  },
  pi: piNotInstalled,
  gh: optionalCliNotInstalled,
};

const ghInstalledAuthed: DependenciesStatus = {
  ...managedUpToDate,
  gh: ghInstalled,
};

const ghNotAuthed: DependenciesStatus = {
  ...managedUpToDate,
  gh: ghInstalledNotAuthed,
};

const Wrapper = ({ deps }: { deps: DependenciesStatus }): ReactElement => {
  const store = createStore();
  store.set(dependenciesStatusAtom, deps);
  return (
    <JotaiProvider store={store}>
      <div style={{ width: "700px" }}>
        <DependenciesSettingsSection
          onSettingChange={async (field, value) => {
            console.log("Setting changed:", field, value);
          }}
        />
      </div>
    </JotaiProvider>
  );
};

const meta = {
  title: "Custom/DependenciesSettingsSection",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const ManagedUpToDate: Story = {
  args: { deps: managedUpToDate },
};

export const ManagedOutOfRange: Story = {
  args: { deps: managedOutOfRange },
};

export const PathMode: Story = {
  args: { deps: pathMode },
};

export const CustomMode: Story = {
  args: { deps: customMode },
};

export const GithubCliInstalledAndAuthed: Story = {
  args: { deps: ghInstalledAuthed },
};

export const GithubCliInstalledNotAuthed: Story = {
  args: { deps: ghNotAuthed },
};

export const NothingInstalled: Story = {
  args: { deps: notInstalled },
};

export const InstallingWithProgress: Story = {
  args: { deps: withInstallProgress },
};

export const ManagedUpgradeFailed: Story = {
  args: { deps: managedUpgradeFailed },
};
