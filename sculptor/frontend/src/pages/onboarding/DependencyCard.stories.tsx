import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { DependencyCard } from "./DependencyCard.tsx";

const meta = {
  title: "Custom/Onboarding/DependencyCard",
  component: DependencyCard,
  args: {
    name: "Claude Code CLI",
    cliName: "claude",
    installUrl: "https://docs.anthropic.com/en/docs/claude-code/getting-started",
    brewPackage: "claude-code",
  },
} satisfies Meta<typeof DependencyCard>;

// eslint-disable-next-line import/no-default-export
export default meta;
type Story = StoryObj<typeof meta>;

export const Loading: Story = {
  args: {
    status: { state: "loading" },
  },
};

export const Installed: Story = {
  args: {
    status: {
      state: "installed",
      path: "/Users/dev/.local/bin/claude",
      version: "2.1.85",
    },
    onApplyOverride: async () => {},
  },
};

export const NotInstalled: Story = {
  args: {
    status: { state: "not-installed" },
    onApplyOverride: async () => {},
  },
};

export const Installing: Story = {
  args: {
    status: { state: "installing" },
  },
};

export const NeedsAuth: Story = {
  args: {
    status: {
      state: "needs-auth",
      path: "/Users/dev/.local/bin/claude",
      version: "2.1.89",
    },
    onAuthenticate: () => console.log("authenticate clicked"),
    onApplyOverride: async () => {},
  },
};

export const Authenticating: Story = {
  args: {
    status: {
      state: "authenticating",
      path: "/Users/dev/.local/bin/claude",
      version: "2.1.89",
    },
  },
};

// SCU-1502: headless/remote sign-in. After "Sign in" the backend returns a URL
// and leaves the CLI waiting on stdin; the card shows the link to open plus a
// field to paste the code back (instead of relying on a localhost browser
// loopback that can't reach the user in a remote container).
export const NeedsAuthAwaitingCode: Story = {
  args: {
    status: {
      state: "needs-auth",
      path: "/Users/dev/.local/bin/claude",
      version: "2.1.89",
    },
    onAuthenticate: () => console.log("authenticate clicked"),
    authUrl: "https://claude.ai/oauth/authorize?client=sculptor&scope=sign-in",
    onSubmitAuthCode: async (code: string) => console.log("submit code", code),
    onApplyOverride: async () => {},
  },
};

// SCU-1502: the pasted code was rejected (or the CLI errored on submit) — the
// inline error is shown beneath the paste-a-code field.
export const NeedsAuthCodeError: Story = {
  args: {
    status: {
      state: "needs-auth",
      path: "/Users/dev/.local/bin/claude",
      version: "2.1.89",
    },
    onAuthenticate: () => console.log("authenticate clicked"),
    authUrl: "https://claude.ai/oauth/authorize?client=sculptor&scope=sign-in",
    authError: "invalid code",
    onSubmitAuthCode: async (code: string) => console.log("submit code", code),
    onApplyOverride: async () => {},
  },
};

// SCU-1502: starting sign-in failed before a URL was produced — the error is
// surfaced and the "Sign in" button remains available to retry.
export const NeedsAuthStartError: Story = {
  args: {
    status: {
      state: "needs-auth",
      path: "/Users/dev/.local/bin/claude",
      version: "2.1.89",
    },
    onAuthenticate: () => console.log("authenticate clicked"),
    authError: "Sign-in failed. Please try again.",
    onSubmitAuthCode: async (code: string) => console.log("submit code", code),
    onApplyOverride: async () => {},
  },
};

export const WrongVersion: Story = {
  args: {
    status: {
      state: "wrong-version",
      path: "/Users/dev/.local/bin/claude",
      version: "2.0.3",
      requiredVersion: "≥2.1.0",
    },
    onApplyOverride: async () => {},
  },
};

export const Error: Story = {
  args: {
    status: { state: "error", message: "permission denied" },
  },
};

// SCU-1271: what the onboarding card shows when a managed download/upgrade
// fails — the reason is surfaced (instead of a silent fallback to the stale
// binary), with override and "Use System PATH" as recovery paths.
export const DownloadFailed: Story = {
  args: {
    status: {
      state: "error",
      message:
        "Download failed: Server error '503 Service Unavailable' for url 'https://storage.googleapis.com/claude-code-releases/2.1.156/darwin-arm64/claude'",
    },
    onApplyOverride: async () => {},
    onModeSwitch: (mode: string) => console.log("switch to", mode),
    modeControls: [{ label: "Use System PATH", mode: "CUSTOM" }],
  },
};

// SCU-1271: a long managed binary path must stay fully readable in the narrow
// card instead of truncating. Rendered in a constrained width so the path
// overflows a single line.
export const WrongVersionLongPath: Story = {
  decorators: [
    (Story): ReactElement => (
      <div style={{ width: 360 }}>
        <Story />
      </div>
    ),
  ],
  args: {
    status: {
      state: "wrong-version",
      path: "/Users/dev/.sculptor/internal/dependencies/claude/version-2.1.111/claude",
      version: "2.1.111",
      requiredVersion: "2.1.156 – 2.99.99",
    },
    onApplyOverride: async () => {},
  },
};

export const WithModeControls: Story = {
  args: {
    status: {
      state: "installed",
      path: "/Users/dev/.local/bin/claude",
      version: "2.1.89",
    },
    onModeSwitch: (mode: string) => console.log("switch to", mode),
    modeControls: [{ label: "Use System PATH", mode: "PATH" }],
    onApplyOverride: async () => {},
  },
};

export const OptionalNotInstalled: Story = {
  args: {
    name: "GitHub CLI",
    cliName: "gh",
    installUrl: "https://cli.github.com/",
    brewPackage: "gh",
    optional: true,
    status: { state: "not-installed" },
    onApplyOverride: async () => {},
  },
};

export const OptionalInstalled: Story = {
  args: {
    name: "GitHub CLI",
    cliName: "gh",
    installUrl: "https://cli.github.com/",
    brewPackage: "gh",
    optional: true,
    status: {
      state: "installed",
      path: "/opt/homebrew/bin/gh",
      version: "2.65.0",
    },
    onApplyOverride: async () => {},
  },
};

export const InstalledWithOverride: Story = {
  args: {
    status: {
      state: "installed",
      path: "/custom/path/claude",
      version: "2.1.85",
      isOverride: true,
    },
    onApplyOverride: async () => {},
  },
};

export const NotInstalledNoOverride: Story = {
  args: {
    status: { state: "not-installed" },
  },
};
