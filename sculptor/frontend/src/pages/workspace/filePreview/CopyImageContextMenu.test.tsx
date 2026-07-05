import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { CopyImageContextMenu } from "./CopyImageContextMenu";

const copyImageToClipboard = vi.hoisted(() => vi.fn());
vi.mock("~/pages/workspace/filePreview/copyImageToClipboard.ts", () => ({ copyImageToClipboard }));

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CopyImageContextMenu", () => {
  it("renders its child trigger", () => {
    render(
      <CopyImageContextMenu url="blob:img">
        <img alt="thing" data-testid="trigger" />
      </CopyImageContextMenu>,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId("trigger")).toBeInTheDocument();
    // Menu is closed until right-click.
    expect(screen.queryByTestId(ElementIds.FILE_PREVIEW_COPY_IMAGE)).not.toBeInTheDocument();
  });

  it("shows a Copy Image item on right-click and copies the url when selected", async () => {
    copyImageToClipboard.mockResolvedValue(undefined);
    render(
      <CopyImageContextMenu url="blob:img">
        <img alt="thing" data-testid="trigger" />
      </CopyImageContextMenu>,
      { wrapper: Wrapper },
    );

    fireEvent.contextMenu(screen.getByTestId("trigger"));
    const item = await screen.findByTestId(ElementIds.FILE_PREVIEW_COPY_IMAGE);
    expect(item).toHaveTextContent("Copy Image");

    fireEvent.click(item);
    await waitFor(() => expect(copyImageToClipboard).toHaveBeenCalledWith("blob:img"));
  });
});
