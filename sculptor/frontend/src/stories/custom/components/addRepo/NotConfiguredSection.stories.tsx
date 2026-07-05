import { Box } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { NotConfiguredSection } from "~/components/addRepo/NotConfiguredSection.tsx";
import type { RemoteProvider } from "~/components/addRepo/SourceRadioCards.tsx";

// Approximates the dialog's 520px max content width so the section reads
// the way the user will see it inside AddRepoDialog (instead of stretching
// across the Storybook canvas).
const Wrapped = (args: { provider: RemoteProvider }): ReactElement => (
  <Box maxWidth="520px" p="3">
    <NotConfiguredSection provider={args.provider} />
  </Box>
);

const meta = {
  title: "Custom/Onboarding/NotConfiguredSection",
  component: Wrapped,
} satisfies Meta<typeof Wrapped>;

// eslint-disable-next-line import/no-default-export
export default meta;
type Story = StoryObj<typeof meta>;

export const GitHub: Story = {
  args: { provider: "github" },
};
