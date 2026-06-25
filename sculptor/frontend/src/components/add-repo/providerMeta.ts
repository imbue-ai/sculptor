import { GitHubLogoIcon } from "@radix-ui/react-icons";
import type { ComponentType } from "react";

import type { RemoteProvider } from "./SourceRadioCards.tsx";

/** Icon component sized via `width`/`height` — compatible with both Radix and lucide icons. */
export type ProviderIcon = ComponentType<{ width?: number | string; height?: number | string }>;

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
  /** Icon component used in the radio cards. */
  Icon: ProviderIcon;
};

export const PROVIDER_META: Record<RemoteProvider, ProviderMeta> = {
  github: {
    label: "GitHub",
    cliBinary: "gh",
    cliLabel: "GitHub CLI",
    installUrl: "https://github.com/cli/cli#installation",
    authCommand: "gh auth login",
    Icon: GitHubLogoIcon,
  },
};
