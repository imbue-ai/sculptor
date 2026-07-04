import { Flex, RadioCards, Text } from "@radix-ui/themes";
import { FolderIcon } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import type { ProviderIcon } from "./providerMeta.ts";
import { PROVIDER_META } from "./providerMeta.ts";

export type AddRepoSource = "github" | "local";
export type RemoteProvider = "github";

type SourceRadioCardsProps = {
  value: AddRepoSource;
  onValueChange: (value: AddRepoSource) => void;
  disabled?: boolean;
};

type CardConfig = {
  value: AddRepoSource;
  label: string;
  Icon: ProviderIcon;
  testId: ElementIds;
};

// The remote provider pulls its label + icon from PROVIDER_META so adding a new
// provider is a one-file change; the Local card is unique to this picker.
// Local renders first: it's the default source (onboarding is local-repo-first —
// a folder on disk needs no CLI install or auth), so the selected card leads.
const CARDS: ReadonlyArray<CardConfig> = [
  { value: "local", label: "Local Folder", Icon: FolderIcon, testId: ElementIds.ADD_REPO_SOURCE_LOCAL },
  {
    value: "github",
    label: PROVIDER_META.github.label,
    Icon: PROVIDER_META.github.Icon,
    testId: ElementIds.ADD_REPO_SOURCE_GITHUB,
  },
];

export const SourceRadioCards = ({ value, onValueChange, disabled = false }: SourceRadioCardsProps): ReactElement => {
  return (
    <RadioCards.Root
      value={value}
      onValueChange={(next: string) => onValueChange(next as AddRepoSource)}
      disabled={disabled}
      columns="2"
      gap="2"
    >
      {CARDS.map(({ value: cardValue, label, Icon, testId }) => (
        <RadioCards.Item key={cardValue} value={cardValue} data-testid={testId}>
          <Flex direction="column" align="center" gap="2" width="100%">
            <Icon width={20} height={20} />
            <Text size="2" weight="medium">
              {label}
            </Text>
          </Flex>
        </RadioCards.Item>
      ))}
    </RadioCards.Root>
  );
};
