import type { Meta, StoryObj } from "@storybook/react-vite";
import { Provider as JotaiProvider } from "jotai";
import type { ReactElement } from "react";

import { DiffFileHeader } from "~/pages/workspace/components/diffPanel/DiffFileHeader.tsx";

const LONG_PATH = "sculptor/frontend/src/pages/workspace/components/diffPanel/DiffFileHeader.tsx";

type WrapperProps = {
  filePath: string;
  addedLines: number;
  removedLines: number;
  width: number;
};

const Wrapper = ({ filePath, addedLines, removedLines, width }: WrapperProps): ReactElement => (
  <JotaiProvider>
    <div style={{ width, border: "1px solid var(--gray-a5)" }}>
      <DiffFileHeader
        workspaceId="storybook"
        filePath={filePath}
        addedLines={addedLines}
        removedLines={removedLines}
        fileStatus="M"
        isBinary={false}
      />
    </div>
  </JotaiProvider>
);

const meta = {
  title: "Custom/DiffFileHeader",
  component: Wrapper,
  args: {
    filePath: LONG_PATH,
    addedLines: 42,
    removedLines: 7,
    width: 800,
  },
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Wide: Story = {
  args: { width: 800 },
};

export const Medium: Story = {
  args: { width: 500 },
};

export const Narrow: Story = {
  args: { width: 350 },
};

export const VeryNarrow: Story = {
  args: { width: 250 },
};

export const ShortPath: Story = {
  args: { filePath: "sculptor/builder/artifacts.py", width: 400 },
};
