import { CheckCircledIcon, CrossCircledIcon, ExclamationTriangleIcon } from "@radix-ui/react-icons";
import { Callout, Code, Flex, Strong } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { DependencyInfo, JjBlocker, JjReadiness } from "../../../api";
import { ElementIds } from "../../../api";

type BlockerCopy = {
  title: string;
  action: (minimumVersion: string) => string;
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
      `Sculptor needs jj ${minimumVersion} or later. Install the managed copy below, or point Sculptor at a newer jj.`,
  },
  NO_IDENTITY: {
    title: "jj has no author identity.",
    action: () => "Set the name and email jj records on your changes under Author identity below.",
  },
} as const satisfies Record<JjBlocker, BlockerCopy>;

type JjAvailabilityCalloutProps = {
  readiness: JjReadiness;
  jj: DependencyInfo;
  minimumVersion: string;
};

/** JJ_AVAILABLE as the user sees it: which jj Sculptor uses, or what stops it and how to fix that. */
export const JjAvailabilityCallout = ({ readiness, jj, minimumVersion }: JjAvailabilityCalloutProps): ReactElement => {
  if (!readiness.blocker) {
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
  const isIdentityOnly = readiness.blocker === "NO_IDENTITY";
  return (
    <Callout.Root color={isIdentityOnly ? "orange" : "red"} data-testid={ElementIds.JJ_AVAILABILITY}>
      <Callout.Icon>{isIdentityOnly ? <ExclamationTriangleIcon /> : <CrossCircledIcon />}</Callout.Icon>
      <Flex direction="column" gap="1">
        <Callout.Text>
          <Strong>{copy.title}</Strong>
        </Callout.Text>
        {readiness.detail && (
          <Callout.Text>
            <Code size="2">{readiness.detail}</Code>
          </Callout.Text>
        )}
        <Callout.Text>{copy.action(minimumVersion)}</Callout.Text>
      </Flex>
    </Callout.Root>
  );
};
