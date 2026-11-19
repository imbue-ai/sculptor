import { Callout, Link } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";
import type { AgentPromptKind } from "~/common/utils/agentPrompts.ts";

const PROMPT_NAMES: Readonly<Record<AgentPromptKind, string>> = {
  commit: "commit",
  "pr-creation": "PR creation",
};

/**
 * Says, in a git prompt's editor, that a jj workspace is sent this git prompt
 * because no jj prompt is set, and links to the Jujutsu page row where a jj one
 * is set. `onLeave` closes the editor before the page opens.
 */
export const JjPromptFallbackNotice = ({
  kind,
  onLeave,
}: {
  kind: AgentPromptKind;
  onLeave: () => void;
}): ReactElement => {
  const openSettings = useOpenSettings();
  return (
    <Callout.Root size="1" mb="3">
      <Callout.Text>
        No jj {PROMPT_NAMES[kind]} prompt is set, so this jj workspace is sent this git prompt, with Sculptor&apos;s jj
        instructions added.{" "}
        <Link
          href="#"
          onClick={(e) => {
            e.preventDefault();
            onLeave();
            openSettings("JJ", kind);
          }}
        >
          Set a jj {PROMPT_NAMES[kind]} prompt
        </Link>
      </Callout.Text>
    </Callout.Root>
  );
};
