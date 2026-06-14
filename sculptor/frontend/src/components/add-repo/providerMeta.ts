import { GithubIcon, GitlabIcon } from "lucide-react";

import type { RemoteProvider } from "./SourceRadioCards.tsx";

// Single source of truth for per-provider strings, URLs, and icons used across
// the Add Repository surface (AddRepoDialog footer CTA, NotConfiguredSection
// copy, SourceRadioCards icons). Keep all provider branding here so adding a
// new provider is a one-file change.
export type ProviderMeta = {
  /** Human-readable provider name, e.g. "GitHub". */
  label: string;
  /** CLI binary name passed as the `cli=` query param on the settings deep link. */
  cliBinary: string;
  /** Human-readable CLI label used in the NotConfiguredSection heading/copy. */
  cliLabel: string;
  /** Install instructions URL for the CLI. */
  installUrl: string;
  /** Shell command to authenticate the CLI. */
  authCommand: string;
  /** Lucide icon used in the radio cards. Typed against `GithubIcon` for compat. */
  Icon: typeof GithubIcon;
};

export const PROVIDER_META: Record<RemoteProvider, ProviderMeta> = {
  github: {
    label: "GitHub",
    cliBinary: "gh",
    cliLabel: "GitHub CLI",
    installUrl: "https://github.com/cli/cli#installation",
    authCommand: "gh auth login",
    Icon: GithubIcon,
  },
  gitlab: {
    label: "GitLab",
    cliBinary: "glab",
    cliLabel: "GitLab CLI",
    installUrl: "https://gitlab.com/gitlab-org/cli/#installation",
    authCommand: "glab auth login",
    Icon: GitlabIcon,
  },
};
