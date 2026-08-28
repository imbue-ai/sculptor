import { Theme } from "@radix-ui/themes";
import { cleanup, render as rtlRender, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { JumpToBottomButton } from "../JumpToBottomButton.tsx";

// Tooltip (from Radix Themes) requires a TooltipProvider in context — provided
// by the Theme component. useKeybindingDisplayText reads a Jotai atom, so we
// also need a Jotai Provider.
const render = (ui: ReactElement): ReturnType<typeof rtlRender> => {
  const store = createStore();
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );
  return rtlRender(ui, { wrapper: Wrapper });
};

describe("JumpToBottomButton", () => {
  afterEach(() => {
    cleanup();
  });

  const defaultScrollContainerRef = { current: document.createElement("div") };

  it("renders with Jump label", () => {
    render(
      <JumpToBottomButton
        isVisible={true}
        label="jump"
        onClick={vi.fn()}
        scrollContainerRef={defaultScrollContainerRef}
      />,
    );
    expect(screen.getByTestId(ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON)).toHaveTextContent("Jump");
  });

  it("renders with New activity label", () => {
    render(
      <JumpToBottomButton
        isVisible={true}
        label="new"
        onClick={vi.fn()}
        scrollContainerRef={defaultScrollContainerRef}
      />,
    );
    expect(screen.getByTestId(ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON)).toHaveTextContent("New activity");
  });

  it("hides button when not visible", () => {
    render(
      <JumpToBottomButton
        isVisible={false}
        label="jump"
        onClick={vi.fn()}
        scrollContainerRef={defaultScrollContainerRef}
      />,
    );
    const button = screen.getByTestId(ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON);
    expect(button).toHaveAttribute("tabindex", "-1");
    expect(button.closest("[aria-hidden]")).toHaveAttribute("aria-hidden", "true");
  });

  it("calls onClick when clicked", async () => {
    const handleClick = vi.fn();
    render(
      <JumpToBottomButton
        isVisible={true}
        label="jump"
        onClick={handleClick}
        scrollContainerRef={defaultScrollContainerRef}
      />,
    );

    await userEvent.click(screen.getByTestId(ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it("marks button as hidden when visibility changes (focus management scenario)", () => {
    const scrollRef = { current: document.createElement("div") };

    const { rerender } = render(
      <JumpToBottomButton isVisible={true} label="jump" onClick={vi.fn()} scrollContainerRef={scrollRef} />,
    );

    const button = screen.getByTestId(ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON);
    expect(button).toHaveAttribute("tabindex", "0");

    rerender(<JumpToBottomButton isVisible={false} label="jump" onClick={vi.fn()} scrollContainerRef={scrollRef} />);

    expect(button).toHaveAttribute("tabindex", "-1");
    expect(button.closest("[aria-hidden]")).toHaveAttribute("aria-hidden", "true");
  });

  it("has the correct aria-label for the 'jump' variant", () => {
    render(
      <JumpToBottomButton
        isVisible={true}
        label="jump"
        onClick={vi.fn()}
        scrollContainerRef={defaultScrollContainerRef}
      />,
    );
    const button = screen.getByTestId(ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON);
    expect(button).toHaveAttribute("aria-label", "Jump to bottom");
  });

  it("has a distinct aria-label for the 'new activity' variant", () => {
    render(
      <JumpToBottomButton
        isVisible={true}
        label="new"
        onClick={vi.fn()}
        scrollContainerRef={defaultScrollContainerRef}
      />,
    );
    const button = screen.getByTestId(ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON);
    expect(button).toHaveAttribute("aria-label", "Jump to bottom — new activity");
  });

  it("moves focus to the scroll container when button becomes hidden while focused", () => {
    const scrollEl = document.createElement("div");
    scrollEl.tabIndex = -1;
    document.body.appendChild(scrollEl);
    const scrollFocusSpy = vi.spyOn(scrollEl, "focus");
    const scrollRef = { current: scrollEl };

    const { rerender } = render(
      <JumpToBottomButton isVisible={true} label="jump" onClick={vi.fn()} scrollContainerRef={scrollRef} />,
    );

    const button = screen.getByTestId(ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON);
    button.focus();
    expect(document.activeElement).toBe(button);

    // Visibility flips off while the button still has focus.
    rerender(<JumpToBottomButton isVisible={false} label="jump" onClick={vi.fn()} scrollContainerRef={scrollRef} />);

    expect(scrollFocusSpy).toHaveBeenCalled();

    scrollFocusSpy.mockRestore();
    document.body.removeChild(scrollEl);
  });

  it("does not move focus when button becomes hidden but was not focused", () => {
    const scrollEl = document.createElement("div");
    scrollEl.tabIndex = -1;
    document.body.appendChild(scrollEl);
    const scrollFocusSpy = vi.spyOn(scrollEl, "focus");
    const scrollRef = { current: scrollEl };

    const { rerender } = render(
      <JumpToBottomButton isVisible={true} label="jump" onClick={vi.fn()} scrollContainerRef={scrollRef} />,
    );

    // Focus is on document.body, not on the button.
    rerender(<JumpToBottomButton isVisible={false} label="jump" onClick={vi.fn()} scrollContainerRef={scrollRef} />);

    expect(scrollFocusSpy).not.toHaveBeenCalled();

    scrollFocusSpy.mockRestore();
    document.body.removeChild(scrollEl);
  });

  it("tooltip shows 'Jump to bottom' label", async () => {
    const user = userEvent.setup();
    render(
      <JumpToBottomButton
        isVisible={true}
        label="jump"
        onClick={vi.fn()}
        scrollContainerRef={defaultScrollContainerRef}
      />,
    );

    const button = screen.getByTestId(ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON);
    await user.hover(button);

    const rows = await screen.findAllByText("Jump to bottom");
    expect(rows.length).toBeGreaterThan(0);
  });

  it("restores tabindex to 0 when the button becomes visible again", () => {
    const scrollRef = { current: document.createElement("div") };
    const { rerender } = render(
      <JumpToBottomButton isVisible={false} label="jump" onClick={vi.fn()} scrollContainerRef={scrollRef} />,
    );
    const button = screen.getByTestId(ElementIds.ALPHA_JUMP_TO_BOTTOM_BUTTON);
    expect(button).toHaveAttribute("tabindex", "-1");

    rerender(<JumpToBottomButton isVisible={true} label="jump" onClick={vi.fn()} scrollContainerRef={scrollRef} />);
    expect(button).toHaveAttribute("tabindex", "0");
    expect(button.closest("[aria-hidden]")).toHaveAttribute("aria-hidden", "false");
  });
});
