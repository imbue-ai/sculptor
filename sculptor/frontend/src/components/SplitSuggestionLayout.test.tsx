import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { SuggestionProps } from "@tiptap/suggestion";
import type { ReactElement } from "react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SplitSuggestionLayout } from "./SplitSuggestionLayout";
import type { SuggestionListRef } from "./SuggestionListContainer";

// `@tanstack/react-virtual` relies on measuring the scroll container with
// ResizeObserver + getBoundingClientRect, both of which return 0-sized in
// jsdom — mock it through so every item renders.
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }): unknown => ({
    getVirtualItems: (): Array<{ index: number; start: number; size: number; key: number }> =>
      Array.from({ length: count }, (_, i) => ({ index: i, start: i * 24, size: 24, key: i })),
    getTotalSize: (): number => count * 24,
    scrollToIndex: (): void => {},
  }),
}));

afterEach(() => {
  cleanup();
});

type TestItem = {
  id: string;
  label: string;
};

const makeProps = (items: Array<TestItem>): { props: SuggestionProps; command: ReturnType<typeof vi.fn> } => {
  const command = vi.fn();
  const props = {
    items,
    command,
    query: "",
    editor: {} as unknown,
    range: { from: 0, to: 0 },
    clientRect: null,
    decorationNode: null,
  } as unknown as SuggestionProps;
  return { props, command };
};

const pressKey = (ref: React.RefObject<SuggestionListRef>, key: string): boolean => {
  let didHandle = false;
  act(() => {
    const event = { key, shiftKey: false } as unknown as KeyboardEvent;
    didHandle = ref.current!.onKeyDown({ event });
  });
  return didHandle;
};

const renderItem = (item: { label: string }): ReactElement => <span>{item.label}</span>;

describe("SplitSuggestionLayout", () => {
  it("renders a side pane that reflects the initially-active item", () => {
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props } = makeProps(items);
    render(
      <SplitSuggestionLayout
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        sideContent={(active): ReactElement => <div data-testid="side">{(active as TestItem | undefined)?.label}</div>}
      />,
    );
    expect(screen.getByTestId("side").textContent).toBe("Alpha");
  });

  it("updates the side pane when ArrowDown moves selection", () => {
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SplitSuggestionLayout
        ref={ref}
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        sideContent={(active): ReactElement => <div data-testid="side">{(active as TestItem | undefined)?.label}</div>}
      />,
    );
    expect(screen.getByTestId("side").textContent).toBe("Alpha");
    pressKey(ref, "ArrowDown");
    expect(screen.getByTestId("side").textContent).toBe("Bravo");
  });

  it("forwards the ref so callers drive the same onKeyDown contract as SuggestionListContainer", () => {
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SplitSuggestionLayout
        ref={ref}
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        sideContent={(): null => null}
      />,
    );
    pressKey(ref, "Enter");
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
  });

  it("followHover defaults to true — mouse-entering a row moves the active item", () => {
    // This is the load-bearing default: the wrapper defaults followHover on so
    // pickers get hover-driven selection without having to opt in.
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props } = makeProps(items);
    render(
      <SplitSuggestionLayout
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        itemTestId="test-item"
        sideContent={(active): ReactElement => <div data-testid="side">{(active as TestItem | undefined)?.label}</div>}
      />,
    );
    const rows = screen.getAllByTestId("test-item");
    fireEvent.mouseEnter(rows[1]);
    expect(screen.getByTestId("side").textContent).toBe("Bravo");
  });

  it("followHover=false disables the mouse → selection sync (opt-out path)", () => {
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props } = makeProps(items);
    render(
      <SplitSuggestionLayout
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        itemTestId="test-item"
        followHover={false}
        sideContent={(active): ReactElement => <div data-testid="side">{(active as TestItem | undefined)?.label}</div>}
      />,
    );
    const rows = screen.getAllByTestId("test-item");
    fireEvent.mouseEnter(rows[1]);
    // Selection stays on Alpha — the container's followHover branch was not taken.
    expect(screen.getByTestId("side").textContent).toBe("Alpha");
  });

  it("empty items: side pane receives undefined and the list shows the empty state", () => {
    const { props } = makeProps([]);
    let receivedActive: unknown = "not-called";
    render(
      <SplitSuggestionLayout
        props={props}
        rowHeight={24}
        emptyState={<div data-testid="empty">No items</div>}
        renderItem={renderItem}
        sideContent={(active): null => {
          receivedActive = active;
          return null;
        }}
      />,
    );
    expect(screen.getByTestId("empty")).toBeTruthy();
    // sideContent was invoked with `undefined` because items[0] is undefined.
    expect(receivedActive).toBeUndefined();
  });
});
