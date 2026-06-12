import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { SuggestionProps } from "@tiptap/suggestion";
import type { ReactElement } from "react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import type { SuggestionAction, SuggestionListRef } from "./SuggestionListContainer";
import { SuggestionListContainer } from "./SuggestionListContainer";

// `@tanstack/react-virtual` relies on measuring the scroll container with
// ResizeObserver + getBoundingClientRect, both of which return 0-sized in
// jsdom — so the virtualizer renders zero items and clicks/hovers can't
// land on a row. Replace the hook with a pass-through that emits every item
// so DOM-based assertions are possible.
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
  isSectionHeader?: boolean;
  isFirstInList?: boolean;
};

const makeProps = (items: Array<TestItem>): { props: SuggestionProps; command: ReturnType<typeof vi.fn> } => {
  const command = vi.fn();
  // `SuggestionProps` has many fields the container never touches. Cast
  // through unknown so tests only provide what the container reads.
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

const pressKey = (ref: React.RefObject<SuggestionListRef>, key: string, shiftKey = false): boolean => {
  // Wrap in act() so the setState triggered inside onKeyDown flushes before
  // the next assertion — otherwise sideContent/selectedIndex updates lag.
  let didHandle = false;
  act(() => {
    const event = { key, shiftKey } as unknown as KeyboardEvent;
    didHandle = ref.current!.onKeyDown({ event });
  });
  return didHandle;
};

const renderItem = (item: { label: string }): ReactElement => <span>{item.label}</span>;

describe("SuggestionListContainer — keyboard navigation", () => {
  it("Enter commits the first selectable item by default", () => {
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    expect(pressKey(ref, "Enter")).toBe(true);
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "a", action: "select" as SuggestionAction }));
  });

  it("ArrowDown advances selection and Enter commits the new selection", () => {
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
      { id: "c", label: "Charlie" },
    ];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    pressKey(ref, "ArrowDown");
    pressKey(ref, "ArrowDown");
    pressKey(ref, "Enter");
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "c", action: "select" }));
  });

  it("ArrowUp from the first row wraps to the last selectable row", () => {
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    pressKey(ref, "ArrowUp");
    pressKey(ref, "Enter");
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "b" }));
  });

  it("Tab commits the current selection with action=drillIn", () => {
    // Tab is the "drill into folder" action in the file picker. The container
    // doesn't know about folders — it just tags the action so the command
    // handler can branch. This is the contract that powers Tab-drilling.
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    pressKey(ref, "Tab");
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "a", action: "drillIn" }));
  });

  it("Shift+Tab invokes onStepBack and always claims the event", () => {
    // Shift+Tab always claims the event so it doesn't leak to the editor as a
    // focus-shift. When the handler returns true a level is popped; when it
    // returns false the popover stays put at the root and the user can press
    // Escape to close.
    const items: Array<TestItem> = [{ id: "a", label: "Alpha" }];
    const { props } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    const onStepBack = vi.fn().mockReturnValue(true);
    render(
      <SuggestionListContainer
        ref={ref}
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        onStepBack={onStepBack}
      />,
    );
    expect(pressKey(ref, "Tab", true)).toBe(true);
    expect(onStepBack).toHaveBeenCalledTimes(1);
  });

  it("Shift+Tab with no handler still claims the event (no focus leak)", () => {
    const items: Array<TestItem> = [{ id: "a", label: "Alpha" }];
    const { props } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    expect(pressKey(ref, "Tab", true)).toBe(true);
  });

  it("Escape always falls through so the popover closes (does not invoke onStepBack)", () => {
    // TipTap's suggestion plugin treats an unhandled Escape as "close the
    // popover." Returning false is the contract — the plugin only sees
    // "close" when the list doesn't claim the event. Escape is *not* an
    // alias for step-back; that's Shift+Tab's job.
    const items: Array<TestItem> = [{ id: "a", label: "Alpha" }];
    const { props } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    const onStepBack = vi.fn().mockReturnValue(true);
    render(
      <SuggestionListContainer
        ref={ref}
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        onStepBack={onStepBack}
      />,
    );
    expect(pressKey(ref, "Escape")).toBe(false);
    expect(onStepBack).not.toHaveBeenCalled();
  });

  it("Escape with no handler falls through so the popover closes", () => {
    const items: Array<TestItem> = [{ id: "a", label: "Alpha" }];
    const { props } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    expect(pressKey(ref, "Escape")).toBe(false);
  });

  it("Enter with empty items returns false (does not claim event)", () => {
    // Regression guard: when nothing can be committed, Enter must fall
    // through to the editor so the user's natural "submit message" keybind
    // still fires.
    const { props, command } = makeProps([]);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer
        ref={ref}
        props={props}
        rowHeight={24}
        emptyState={<div data-testid="empty-state">No items</div>}
        renderItem={renderItem}
      />,
    );
    expect(pressKey(ref, "Enter")).toBe(false);
    expect(command).not.toHaveBeenCalled();
    expect(screen.getByTestId("empty-state")).toBeTruthy();
  });

  it("Tab with empty items returns false (does not claim event)", () => {
    const { props, command } = makeProps([]);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    expect(pressKey(ref, "Tab")).toBe(false);
    expect(command).not.toHaveBeenCalled();
  });

  it("unknown keys return false so the editor handles them", () => {
    const items: Array<TestItem> = [{ id: "a", label: "Alpha" }];
    const { props } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    expect(pressKey(ref, "a")).toBe(false);
    expect(pressKey(ref, "Escape")).toBe(false);
  });
});

describe("SuggestionListContainer — section headers", () => {
  it("ArrowDown skips section-header rows (non-selectable)", () => {
    // The skill picker interleaves section headers like "Built-in" with
    // selectable skill items. Arrow keys must jump over the headers or the
    // selection would halt on a row the user can't commit.
    const items: Array<TestItem> = [
      { id: "h1", label: "Header 1", isSectionHeader: true, isFirstInList: true },
      { id: "a", label: "Alpha" },
      { id: "h2", label: "Header 2", isSectionHeader: true },
      { id: "b", label: "Bravo" },
    ];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    // Initial selection should land on "a" (first selectable, not the header).
    pressKey(ref, "Enter");
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
    command.mockClear();

    // Down once should jump directly from "a" to "b", skipping "h2".
    pressKey(ref, "ArrowDown");
    pressKey(ref, "Enter");
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "b" }));
  });

  it("Tab/Enter on a section header is a no-op (command not called)", () => {
    // If the starting selection landed on a header (shouldn't, but
    // guard the invariant), committing must not fire.
    const items: Array<TestItem> = [{ id: "h", label: "Header", isSectionHeader: true, isFirstInList: true }];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    pressKey(ref, "Enter");
    expect(command).not.toHaveBeenCalled();
  });

  it("renders section-header rows with aria-hidden so screen readers skip them", () => {
    // Headers are visual-only labels; they should not be announced as
    // navigable items.
    const items: Array<TestItem> = [
      { id: "h1", label: "Header 1", isSectionHeader: true, isFirstInList: true },
      { id: "a", label: "Alpha" },
    ];
    const { props } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    const { container } = render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    const hidden = container.querySelectorAll("[aria-hidden]");
    expect(hidden.length).toBeGreaterThanOrEqual(1);
    expect(hidden[0].textContent).toBe("Header 1");
  });
});

describe("SuggestionListContainer — selection reset on items change", () => {
  it("resets selection to the first selectable row when items identity changes", () => {
    // The picker re-queries the items list on every keystroke. Without this
    // reset, the selected index would cling to a stale row past the new list
    // length (causing a no-op commit) or point at the wrong item entirely.
    const ref = createRef<SuggestionListRef>();

    const firstItems: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
      { id: "c", label: "Charlie" },
    ];
    const cmd1 = vi.fn();
    const props1 = {
      items: firstItems,
      command: cmd1,
      query: "",
      editor: {} as unknown,
      range: { from: 0, to: 0 },
      clientRect: null,
      decorationNode: null,
    } as unknown as SuggestionProps;
    const { rerender } = render(
      <SuggestionListContainer ref={ref} props={props1} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    // Move selection to index 2 ("c").
    pressKey(ref, "ArrowDown");
    pressKey(ref, "ArrowDown");

    // Re-render with a new items array (different identity).
    const secondItems: Array<TestItem> = [
      { id: "x", label: "X-ray" },
      { id: "y", label: "Yankee" },
    ];
    const cmd2 = vi.fn();
    const props2 = {
      items: secondItems,
      command: cmd2,
      query: "",
      editor: {} as unknown,
      range: { from: 0, to: 0 },
      clientRect: null,
      decorationNode: null,
    } as unknown as SuggestionProps;
    rerender(
      <SuggestionListContainer ref={ref} props={props2} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );

    pressKey(ref, "Enter");
    // After items change, selection should have reset to the first row.
    expect(cmd2).toHaveBeenCalledWith(expect.objectContaining({ id: "x" }));
  });
});

describe("SuggestionListContainer — mouse interaction", () => {
  it("clicking a row commits that row with action=select", () => {
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer
        ref={ref}
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        itemTestId="test-item"
      />,
    );
    const rows = screen.getAllByTestId("test-item");
    fireEvent.click(rows[1]);
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "b" }));
  });

  it("clicking a drillable row drills in (action=drillIn), leaf rows still commit", () => {
    // SCU-1296: a click is a single gesture, so drill-capable rows (e.g. a
    // workspace or folder with a deeper level) need to drill on click to match
    // the keyboard's Tab/ArrowRight. The consumer marks which rows drill via
    // isRowDrillable; everything else commits with action=select.
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer
        ref={ref}
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        itemTestId="test-item"
        isRowDrillable={(item) => item.id === "a"}
      />,
    );
    const rows = screen.getAllByTestId("test-item");
    fireEvent.click(rows[0]);
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "a", action: "drillIn" }));
    command.mockClear();
    fireEvent.click(rows[1]);
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "b", action: "select" }));
  });

  it("with followHover=true, hovering a row moves the selection", () => {
    // The skill picker uses followHover so its detail pane tracks whichever
    // row is under the mouse. Without this, mouse users would see a stale
    // detail pane pinned to the last keyboard-selected row.
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer
        ref={ref}
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        itemTestId="test-item"
        followHover
      />,
    );
    const rows = screen.getAllByTestId("test-item");
    fireEvent.mouseEnter(rows[1]);
    pressKey(ref, "Enter");
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "b" }));
  });

  it("without followHover, hovering does not move selection", () => {
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props, command } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer
        ref={ref}
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        itemTestId="test-item"
      />,
    );
    const rows = screen.getAllByTestId("test-item");
    fireEvent.mouseEnter(rows[1]);
    pressKey(ref, "Enter");
    // Hover should NOT have selected "b" — selection stays on "a".
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
  });
});

describe("SuggestionListContainer — side content", () => {
  it("renders sideContent with the currently-active item and updates on ArrowDown", () => {
    const items: Array<TestItem> = [
      { id: "a", label: "Alpha" },
      { id: "b", label: "Bravo" },
    ];
    const { props } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    const sideContent = (activeItem: TestItem | undefined): ReactElement | null =>
      activeItem ? <div data-testid="side-pane">{activeItem.label}</div> : null;
    render(
      <SuggestionListContainer
        ref={ref}
        props={props}
        rowHeight={24}
        emptyState={<div />}
        renderItem={renderItem}
        sideContent={sideContent as never}
      />,
    );
    expect(screen.getByTestId("side-pane").textContent).toBe("Alpha");
    pressKey(ref, "ArrowDown");
    expect(screen.getByTestId("side-pane").textContent).toBe("Bravo");
  });

  it("renders the list test id on the root container", () => {
    // Integration tests locate the popover via ElementIds.MENTION_LIST; this
    // guards that the data-testid still matches the ElementIds constant.
    const items: Array<TestItem> = [{ id: "a", label: "Alpha" }];
    const { props } = makeProps(items);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    expect(screen.getByTestId(ElementIds.MENTION_LIST)).toBeTruthy();
  });

  it("renders the list test id on the empty-state container too", () => {
    // Empty state must also carry the test id — otherwise integration tests
    // that wait for the popover to be "visible" with the MENTION_LIST id
    // would time out on empty lists (e.g. no-match state).
    const { props } = makeProps([]);
    const ref = createRef<SuggestionListRef>();
    render(
      <SuggestionListContainer ref={ref} props={props} rowHeight={24} emptyState={<div />} renderItem={renderItem} />,
    );
    expect(screen.getByTestId(ElementIds.MENTION_LIST)).toBeTruthy();
  });
});
