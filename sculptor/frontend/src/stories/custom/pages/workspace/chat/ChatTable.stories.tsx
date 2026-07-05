import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactElement } from "react";

import { ChatTable } from "~/pages/workspace/chat/ChatTable.tsx";

const meta = {
  title: "Chat/Content/Table",
  component: ChatTable,
  decorators: [
    (Story): ReactElement => (
      <div style={{ padding: "16px", maxWidth: "700px" }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof ChatTable>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Basic: Story = {
  args: {
    children: (
      <>
        <thead>
          <tr>
            <th>Name</th>
            <th>Role</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Alice</td>
            <td>Engineer</td>
            <td>Active</td>
          </tr>
          <tr>
            <td>Bob</td>
            <td>Designer</td>
            <td>Active</td>
          </tr>
          <tr>
            <td>Charlie</td>
            <td>PM</td>
            <td>On leave</td>
          </tr>
        </tbody>
      </>
    ),
  },
};

export const ManyColumns: Story = {
  args: {
    children: (
      <>
        <thead>
          <tr>
            <th>Col 1</th>
            <th>Col 2</th>
            <th>Col 3</th>
            <th>Col 4</th>
            <th>Col 5</th>
            <th>Col 6</th>
            <th>Col 7</th>
            <th>Col 8</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>data</td>
            <td>data</td>
            <td>data</td>
            <td>data</td>
            <td>data</td>
            <td>data</td>
            <td>data</td>
            <td>data</td>
          </tr>
          <tr>
            <td>more</td>
            <td>more</td>
            <td>more</td>
            <td>more</td>
            <td>more</td>
            <td>more</td>
            <td>more</td>
            <td>more</td>
          </tr>
        </tbody>
      </>
    ),
  },
  decorators: [
    (Story): ReactElement => (
      <div style={{ padding: "16px", maxWidth: "400px" }}>
        <Story />
      </div>
    ),
  ],
};

export const ManyRows: Story = {
  args: {
    children: (
      <>
        <thead>
          <tr>
            <th>#</th>
            <th>Feature</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 12 }, (_, i) => (
            <tr key={i}>
              <td>{i + 1}</td>
              <td>Feature {i + 1}</td>
              <td>{i % 3 === 0 ? "Done" : i % 3 === 1 ? "In progress" : "Planned"}</td>
            </tr>
          ))}
        </tbody>
      </>
    ),
  },
};

export const SingleRow: Story = {
  args: {
    children: (
      <>
        <thead>
          <tr>
            <th>Key</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>version</td>
            <td>1.0.0</td>
          </tr>
        </tbody>
      </>
    ),
  },
};
