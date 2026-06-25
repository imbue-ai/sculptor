import { Dialog } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { CloneProgressView } from "~/components/add-repo/CloneProgressView.tsx";

// The real CloneProgressView lives inside a Radix Dialog.Content, so wrap it
// here for accurate sizing/typography. Each story controls its own dialog.
const Wrapped = (args: { displayName: string; webUrl?: string }): ReactElement => (
  <Dialog.Root open>
    <Dialog.Content maxWidth="520px">
      <CloneProgressView displayName={args.displayName} webUrl={args.webUrl} />
    </Dialog.Content>
  </Dialog.Root>
);

const meta = {
  title: "Custom/Onboarding/CloneProgressView",
  component: Wrapped,
} satisfies Meta<typeof Wrapped>;

// eslint-disable-next-line import/no-default-export
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    displayName: "imbue-ai/sculptor",
    webUrl: "https://github.com/imbue-ai/sculptor",
  },
};

export const NestedGroupPath: Story = {
  args: {
    displayName: "group/subgroup/long-project-name-here",
    webUrl: "https://github.com/group/subgroup/long-project-name-here",
  },
};

export const NoWebUrl: Story = {
  args: {
    displayName: "owner/repo",
  },
};
