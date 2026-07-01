import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ExplorerLayout } from "./ExplorerLayout";

afterEach(() => {
  cleanup();
});

const renderLayout = (): void => {
  render(
    <Theme>
      <ExplorerLayout
        list={<div data-testid="list-slot">list</div>}
        detail={(toggle) => (
          <div data-testid="detail-slot">
            {toggle}
            detail
          </div>
        )}
      />
    </Theme>,
  );
};

describe("ExplorerLayout — fixed-width sidebar", () => {
  it("renders both slots", () => {
    renderLayout();
    expect(screen.getByTestId("list-slot")).toBeInTheDocument();
    expect(screen.getByTestId("detail-slot")).toBeInTheDocument();
  });

  it("does not render a user-resizable divider (the sidebar is a fixed width)", () => {
    renderLayout();
    // A ResizeHandle renders role="separator"; the fixed-width sidebar must not
    // have one, so the pane cannot be dragged to a new size.
    expect(screen.queryByRole("separator")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Resize sidebar")).not.toBeInTheDocument();
  });

  it("gives the list pane a fixed pixel width", () => {
    renderLayout();
    const listPane = screen.getByTestId("list-slot").parentElement;
    expect(listPane).not.toBeNull();
    // The pane sets an explicit pixel width so it never flex-grows or shrinks.
    expect(listPane?.style.width).toMatch(/^\d+px$/);
  });
});
