import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { HoverCard } from "./HoverCard";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

afterEach(() => {
  cleanup();
});

// HoverCard guards against spurious opens by requiring a document-level
// mousemove before honoring hover events — without this, a chip that mounts
// under a stationary pointer would fan its card open immediately. Tests that
// want to exercise the hover path must simulate the initial move first.
const simulateUserMove = (): void => {
  fireEvent.mouseMove(document);
};

describe("HoverCard — forceOpen", () => {
  it("forceOpen=true pins the card open without any hover", () => {
    render(
      <Wrapper>
        <HoverCard
          forceOpen
          trigger={<span data-testid="trigger">trigger</span>}
          content={<div data-testid="content">pinned content</div>}
        />
      </Wrapper>,
    );
    expect(screen.getByTestId("content")).toBeTruthy();
  });

  it("forceOpen=false does not open without hover", () => {
    render(
      <Wrapper>
        <HoverCard
          trigger={<span data-testid="trigger">trigger</span>}
          content={<div data-testid="content">content</div>}
        />
      </Wrapper>,
    );
    expect(screen.queryByTestId("content")).toBeNull();
  });

  it("forceOpen overrides suppressHover (pinned chip still renders its card)", () => {
    // When a chip is node-selected, the editor sets forceOpen=true even if
    // the range-selection suppressHover flag is also on. The pinned card must
    // still show so keyboard-selected chips surface their popover.
    render(
      <Wrapper>
        <HoverCard
          forceOpen
          suppressHover
          trigger={<span data-testid="trigger">trigger</span>}
          content={<div data-testid="content">pinned</div>}
        />
      </Wrapper>,
    );
    expect(screen.getByTestId("content")).toBeTruthy();
  });

  it("toggling forceOpen off removes the card", () => {
    const { rerender } = render(
      <Wrapper>
        <HoverCard
          forceOpen
          trigger={<span data-testid="trigger">trigger</span>}
          content={<div data-testid="content">pinned</div>}
        />
      </Wrapper>,
    );
    expect(screen.getByTestId("content")).toBeTruthy();
    rerender(
      <Wrapper>
        <HoverCard
          forceOpen={false}
          trigger={<span data-testid="trigger">trigger</span>}
          content={<div data-testid="content">pinned</div>}
        />
      </Wrapper>,
    );
    expect(screen.queryByTestId("content")).toBeNull();
  });
});

describe("HoverCard — suppressHover", () => {
  it("suppressHover blocks the hover-open path", () => {
    // Regression: editor Cmd+A should not fan out every chip's hover card.
    // suppressHover on its own must make hover a no-op.
    render(
      <Wrapper>
        <HoverCard
          suppressHover
          openDelay={0}
          trigger={<span data-testid="trigger">trigger</span>}
          content={<div data-testid="content">content</div>}
        />
      </Wrapper>,
    );
    simulateUserMove();
    const trigger = screen.getByTestId("trigger");
    fireEvent.pointerEnter(trigger);
    fireEvent.mouseEnter(trigger);
    // Hover-open was suppressed, so content must not render.
    expect(screen.queryByTestId("content")).toBeNull();
  });
});

describe("HoverCard — mount-time move guard", () => {
  it("does NOT open on the first pointer-enter if the user hasn't moved yet", () => {
    // A chip that appears under a stationary pointer would otherwise open
    // immediately because the browser synthesizes pointerenter. The guard
    // ignores the first open attempt until `mousemove` fires on document.
    render(
      <Wrapper>
        <HoverCard
          openDelay={0}
          trigger={<span data-testid="trigger">trigger</span>}
          content={<div data-testid="content">content</div>}
        />
      </Wrapper>,
    );
    const trigger = screen.getByTestId("trigger");
    fireEvent.pointerEnter(trigger);
    fireEvent.mouseEnter(trigger);
    // No mousemove on document yet — open is suppressed.
    expect(screen.queryByTestId("content")).toBeNull();
  });
});

describe("HoverCard — group coordination", () => {
  it("renders multiple group-linked cards without crashing on mount/unmount", () => {
    // Group coordination happens via a module-level Map. This guards that
    // mounting and unmounting group-linked cards doesn't leak state or
    // throw (e.g. double-close / double-register).
    const groupId = `test-group-${Math.random()}`;
    const { unmount } = render(
      <Wrapper>
        <HoverCard
          group={groupId}
          forceOpen
          trigger={<span data-testid="a-trigger">a</span>}
          content={<div data-testid="a-content">A</div>}
        />
        <HoverCard
          group={groupId}
          forceOpen
          trigger={<span data-testid="b-trigger">b</span>}
          content={<div data-testid="b-content">B</div>}
        />
      </Wrapper>,
    );
    // Both cards are pinned open.
    expect(screen.getByTestId("a-content")).toBeTruthy();
    expect(screen.getByTestId("b-content")).toBeTruthy();
    // Clean unmount should not throw even though both contributed to the
    // group's openCount.
    expect(() => unmount()).not.toThrow();
  });

  it("cards without a group remain independent", () => {
    render(
      <Wrapper>
        <HoverCard
          forceOpen
          trigger={<span data-testid="a-trigger">a</span>}
          content={<div data-testid="a-content">A</div>}
        />
        <HoverCard trigger={<span data-testid="b-trigger">b</span>} content={<div data-testid="b-content">B</div>} />
      </Wrapper>,
    );
    // Only A is pinned open. B did not hover, so it must stay closed.
    expect(screen.getByTestId("a-content")).toBeTruthy();
    expect(screen.queryByTestId("b-content")).toBeNull();
  });
});
