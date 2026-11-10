import { Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { JjIdentity, JjReadiness } from "../../../api";
import { ElementIds } from "../../../api";
import { JjIdentityForm } from "./JjIdentityForm.tsx";
import { SettingRow } from "./SettingRow.tsx";

type JjIdentityRowProps = {
  readiness: JjReadiness;
  onSave: (identity: JjIdentity) => Promise<void>;
};

export const JjIdentityRow = ({ readiness, onSave }: JjIdentityRowProps): ReactElement => (
  <SettingRow
    title="Author identity"
    description="The name and email jj records on your changes, read from your jj config the way agents see it."
  >
    {readiness.blocker === null ? (
      <Text size="2" data-testid={ElementIds.JJ_IDENTITY}>
        {`${readiness.identity.name} <${readiness.identity.email}>`}
      </Text>
    ) : readiness.blocker === "NO_IDENTITY" ? (
      // Remounting on a new suggestion restarts the drafts from it.
      <JjIdentityForm
        key={`${readiness.suggestedIdentity.name}\n${readiness.suggestedIdentity.email}`}
        suggestion={readiness.suggestedIdentity}
        onSave={onSave}
      />
    ) : (
      <Text size="2" color="gray" data-testid={ElementIds.JJ_IDENTITY}>
        Read once jj is installed and runs.
      </Text>
    )}
  </SettingRow>
);
