import { Callout, Link } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { AgentPromptKind } from "~/common/utils/agentPrompts.ts";

const PROMPT_NAMES: Readonly<Record<AgentPromptKind, string>> = {
  commit: "commit",
  "pr-creation": "PR creation",
};

/**
 * Says, in a git prompt's editor, that a jj workspace is sent this git prompt
 * because no jj prompt is set, and links to where a jj one is set.
 */
export const JjPromptFallbackNotice = ({
  kind,
  onOpenJjPrompt,
}: {
  kind: AgentPromptKind;
  onOpenJjPrompt: () => void;
}): ReactElement => (
  <Callout.Root size="1" mb="3">
    <Callout.Text>
      No jj {PROMPT_NAMES[kind]} prompt is set, so this jj workspace is sent this git prompt, with Sculptor&apos;s jj
      instructions added.{" "}
      <Link
        href="#"
        onClick={(e) => {
          e.preventDefault();
          onOpenJjPrompt();
        }}
      >
        Set a jj {PROMPT_NAMES[kind]} prompt
      </Link>
    </Callout.Text>
  </Callout.Root>
);
