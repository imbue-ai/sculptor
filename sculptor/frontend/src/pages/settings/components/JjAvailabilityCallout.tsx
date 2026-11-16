import { CheckCircledIcon, CrossCircledIcon, ExclamationTriangleIcon } from "@radix-ui/react-icons";
import { Callout, Code, Flex, Strong } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { DependencyInfo, JjAvailable, JjReadiness } from "../../../api";
import { ElementIds } from "../../../api";

type JjBlocker = NonNullable<JjReadiness["blocker"]>;

type BlockerCopy = {
  title: string;
  /** Takes the oldest version of the tool the blocker is about. */
  action: (requiredVersion: string) => string;
};

const BLOCKER_COPY = {
  NOT_INSTALLED: {
    title: "jj is not installed.",
    action: () => "Install the managed copy below, or switch Binary Source to Custom and set the path to your own jj.",
  },
  NOT_RUNNABLE: {
    title: "jj is installed but does not run.",
    action: () => "Fix the error above, then Re-check.",
  },
  UNSUPPORTED_VERSION: {
    title: "This jj version is not supported.",
    action: (minimumVersion) =>
      `Sculptor needs jj ${minimumVersion} or a newer compatible version. Install the managed copy below, or point Sculptor at a compatible jj.`,
  },
  UNSUPPORTED_GIT: {
    title: "jj cannot fetch or push with the git it finds.",
    action: (minimumVersion) =>
      `jj needs git ${minimumVersion} or newer. Install one first on your PATH, or set jj's git.executable-path to it, then Re-check.`,
  },
  NO_IDENTITY: {
    title: "jj has no author identity.",
    action: () => "Set the name and email jj records on your changes under Author identity below.",
  },
  SHADOWED: {
    title: "Your login shell runs a jj that Sculptor does not support.",
    action: (minimumVersion) =>
      `Sculptor needs jj ${minimumVersion} or a newer compatible version, because your repositories are shared with the jj you run yourself. Upgrade or remove this jj, or stop your shell profile putting its directory first on PATH, then Re-check.`,
  },
} as const satisfies Record<JjBlocker, BlockerCopy>;

/** The failing check's finding, for the blockers that carry one. */
const describeFinding = (readiness: Exclude<JjReadiness, JjAvailable>): string | null => {
  switch (readiness.blocker) {
    case "NOT_RUNNABLE":
      return readiness.error;
    case "UNSUPPORTED_VERSION":
    case "SHADOWED":
      return readiness.version === null
        ? `${readiness.path} reports no recognizable jj version`
        : `${readiness.path} reports jj ${readiness.version}`;
    case "UNSUPPORTED_GIT":
      if (readiness.path === null) {
        return "jj finds no git";
      }
      return readiness.version === null
        ? `${readiness.path} reports no recognizable git version`
        : `${readiness.path} reports git ${readiness.version}`;
    case "NOT_INSTALLED":
    case "NO_IDENTITY":
      return null;
  }
};

type JjAvailabilityCalloutProps = {
  readiness: JjReadiness;
  jj: DependencyInfo;
  minimumVersion: string;
};

/** JJ_AVAILABLE as the user sees it: which jj Sculptor uses, or what stops it and how to fix that. */
export const JjAvailabilityCallout = ({ readiness, jj, minimumVersion }: JjAvailabilityCalloutProps): ReactElement => {
  if (readiness.blocker === null) {
    const source = jj.source === "MANAGED" ? "managed by Sculptor" : `from ${jj.path}`;
    return (
      <Callout.Root color="green" data-testid={ElementIds.JJ_AVAILABILITY}>
        <Callout.Icon>
          <CheckCircledIcon />
        </Callout.Icon>
        <Callout.Text>
          jj {jj.version} is available, {source}.
        </Callout.Text>
      </Callout.Root>
    );
  }

  const copy = BLOCKER_COPY[readiness.blocker];
  const finding = describeFinding(readiness);
  const isIdentityOnly = readiness.blocker === "NO_IDENTITY";
  return (
    <Callout.Root color={isIdentityOnly ? "orange" : "red"} data-testid={ElementIds.JJ_AVAILABILITY}>
      <Callout.Icon>{isIdentityOnly ? <ExclamationTriangleIcon /> : <CrossCircledIcon />}</Callout.Icon>
      <Flex direction="column" gap="1">
        <Callout.Text>
          <Strong>{copy.title}</Strong>
        </Callout.Text>
        {finding && (
          <Callout.Text>
            <Code size="2">{finding}</Code>
          </Callout.Text>
        )}
        <Callout.Text>
          {copy.action(readiness.blocker === "UNSUPPORTED_GIT" ? readiness.minimumVersion : minimumVersion)}
        </Callout.Text>
      </Flex>
    </Callout.Root>
  );
};
