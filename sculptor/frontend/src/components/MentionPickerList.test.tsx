import { Theme } from "@radix-ui/themes";
import { act, cleanup, render } from "@testing-library/react";
import type { SuggestionProps } from "@tiptap/suggestion";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createRef, StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MentionPickerList } from "./MentionPickerList";
import type { MentionPickerCategoryRow, MentionPickerSubConfigs } from "./MentionPickerSuggestion";
import { createMentionPickerSuggestion } from "./MentionPickerSuggestion";
import type { SuggestionListRef } from "./SuggestionListContainer";

// `@tanstack/react-virtual` measures via ResizeObserver/getBoundingClientRect
// which return 0-sized in jsdom. Pass items through directly so DOM-based
// assertions and click/hover handlers are reachable.
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }): unknown => ({
    getVirtualItems: (): Array<{ index: number; start: number; size: number; key: number }> =>
      Array.from({ length: count }, (_, i) => ({ index: i, start: i * 26, size: 26, key: i })),
    getTotalSize: (): number => count * 26,
    scrollToIndex: (): void => {},
  }),
}));

// Stub the skills SDK call so `createSkillSuggestion`'s eager prefetch
// doesn't log a "Failed to parse URL" error from undici when run under
// jsdom (no base URL). The data shape is unused by these tests.
vi.mock("../api", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../api");
  return { ...actual, getSkills: (): Promise<{ data: [] }> => Promise.resolve({ data: [] }) };
});

const makeMockEditor = (): unknown => {
  const chain = {
    focus: (): unknown => chain,
    deleteRange: (): unknown => chain,
    insertContentAt: (): unknown => chain,
    run: (): void => {},
  };
  return { chain: (): unknown => chain };
};

// Build a suggestion-config skeleton sufficient to drive the items() filter
// without standing up a real TipTap editor. The entity ref is provided so all
// six categories are available; the command/render/pluginKey fields aren't
// exercised by these tests.
const makeFullPickerConfig = (): ReturnType<typeof createMentionPickerSuggestion> =>
  createMentionPickerSuggestion({
    projectID: "proj-1",
    workspaceID: "ws-1",
    entityDataRef: { current: { repositories: [], workspaces: [], agents: [] } },
    onTriggerImageUpload: vi.fn(),
    triggerChar: "+",
  });

const runItemsFilter = async (query: string): Promise<Array<MentionPickerCategoryRow>> => {
  const config = makeFullPickerConfig();
  const editor = makeMockEditor() as Parameters<NonNullable<typeof config.items>>[0]["editor"];
  // `items` returns either a sync array or a promise depending on the picker;
  // wrap with Promise.resolve so the test body stays uniform.
  const result = await Promise.resolve(
    config.items?.({ query, editor }) as Promise<Array<MentionPickerCategoryRow>> | Array<MentionPickerCategoryRow>,
  );
  return result;
};

afterEach(() => {
  cleanup();
});

describe("createMentionPickerSuggestion — items() filter", () => {
  it("ignores description / iconName text — '+work' must not return 'Files & folders'", async () => {
    // Bug regression: an earlier filter matched description and iconName too,
    // so '+work' surfaced 'Files & folders' (description: 'Search workspace
    // files and folders'). The filter must be label-only so the visible name
    // is the only thing that controls ranking.
    const items = await runItemsFilter("work");
    const labels = items.map((row) => row.label);
    expect(labels).not.toContain("Files & folders");
    expect(labels).toContain("Workspaces and Agents");
  });

  it("'+age' returns only the Workspaces-and-Agents and Images rows (label substring matches)", async () => {
    // The standalone "Agents" category was retired — agents are reached by
    // drilling into a workspace inside the "Workspaces and Agents" picker.
    // The "age" substring still matches that row's label and "Images".
    const items = await runItemsFilter("age");
    const labels = items.map((row) => row.label);
    expect(labels).toEqual(["Workspaces and Agents", "Images"]);
  });

  it("empty query returns every available category", async () => {
    const items = await runItemsFilter("");
    // 5 categories: Files & folders, Skills, Workspaces and Agents,
    // Repositories, Images. The previous standalone Agents row was folded
    // into "Workspaces and Agents".
    expect(items).toHaveLength(5);
  });

  it("'+file' returns Files & folders only", async () => {
    const items = await runItemsFilter("file");
    expect(items.map((row) => row.label)).toEqual(["Files & folders"]);
  });

  it("matching is case-insensitive", async () => {
    const items = await runItemsFilter("AGEN");
    expect(items.map((row) => row.label)).toEqual(["Workspaces and Agents"]);
  });
});

// MentionPickerList is the React component the popover hosts. The bug repros only when
// MentionPickerList is in the loop: the user filtered, navigated, then filtered again,
// and the selection-index lagged behind the new items. We render MentionPickerList
// directly with the suggestion-shape props TipTap would normally inject, then
// re-render with a filtered items array — the same "rerender props" pattern
// TipTap drives via `reactRenderer.updateProps`.
// Production renders the editor tree inside `<React.StrictMode>` (see
// `Main.tsx`), which double-invokes function components in dev. The
// suggestion-list's selection-reset has to survive that — a render-time
// `useRef` mutation would persist across the discarded first render and
// make the second render skip the reset, leaving selection on the stale
// row. Wrapping every test in `<StrictMode>` makes the harness match
// production and catches that regression.
describe("MentionPickerList — selection resets when the filtered items change", () => {
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <StrictMode>
      <Provider store={createStore()}>
        <Theme>{children}</Theme>
      </Provider>
    </StrictMode>
  );

  const makeProps = (
    items: Array<MentionPickerCategoryRow>,
    query: string,
  ): { props: SuggestionProps; command: ReturnType<typeof vi.fn> } => {
    const command = vi.fn();
    const props = {
      items,
      command,
      query,
      editor: makeMockEditor(),
      range: { from: 0, to: 1 },
      clientRect: null,
      decorationNode: null,
    } as unknown as SuggestionProps;
    return { props, command };
  };

  const subConfigs: MentionPickerSubConfigs = {};

  const pressKey = (ref: React.RefObject<SuggestionListRef>, key: string): void => {
    act(() => {
      ref.current!.onKeyDown({ event: { key, shiftKey: false } as unknown as KeyboardEvent });
    });
  };

  it("after Down + filter, Tab does not fall through to the stale 'Images' row", async () => {
    // Reproduces the user's bug-2 scenario:
    //   1. Type '+' → all available categories visible.
    //   2. Press Down → selection on row 1 ("Skills").
    //   3. Type "age" → items shrink to ["Workspaces and Agents", "Images"].
    //      Selection must reset to row 0 so Tab drills into the entity
    //      picker — not Images, which would be the stale row 1 and trigger
    //      the upload dialog.
    const allCategories = await runItemsFilter("");
    const ageCategories = await runItemsFilter("age");
    expect(ageCategories.map((row) => row.label)).toEqual(["Workspaces and Agents", "Images"]);

    const { props: initialProps } = makeProps(allCategories, "");
    const onTriggerImageUpload = vi.fn();
    const ref = createRef<SuggestionListRef>();

    const { rerender } = render(
      <Wrapper>
        <MentionPickerList
          ref={ref}
          subConfigs={subConfigs}
          onTriggerImageUpload={onTriggerImageUpload}
          triggerChar="+"
          {...initialProps}
        />
      </Wrapper>,
    );

    pressKey(ref, "ArrowDown");

    const { props: filteredProps } = makeProps(ageCategories, "age");
    rerender(
      <Wrapper>
        <MentionPickerList
          ref={ref}
          subConfigs={subConfigs}
          onTriggerImageUpload={onTriggerImageUpload}
          triggerChar="+"
          {...filteredProps}
        />
      </Wrapper>,
    );

    pressKey(ref, "Tab");
    // Tab on the stale index 1 ("Images") would have fired the upload
    // dialog. Tab on the reset index 0 ("Workspaces and Agents") drills
    // into the entity picker instead, leaving onTriggerImageUpload
    // untouched.
    expect(onTriggerImageUpload).not.toHaveBeenCalled();
  });

  it("after Down twice + filter, Tab drills into the new first row instead of no-op'ing past the end", async () => {
    // Reproduces the user's bug-3 scenario: from the unfiltered list press
    // Down twice (sel = 2 = "Workspaces and Agents"), then type "age" →
    // list shrinks to two entries. A stale index of 2 would point past
    // the end and Tab would silently no-op (the container drops out when
    // items[index] is undefined). With the reset working, Tab on the new
    // index 0 fires the editor chain to drill into that category.
    const allCategories = await runItemsFilter("");
    const ageCategories = await runItemsFilter("age");

    // Build a chain mock whose `run` we can spy on so we can distinguish
    // "Tab no-op" from "Tab drilled in successfully".
    const runSpy = vi.fn();
    const chain = {
      focus: (): unknown => chain,
      deleteRange: (): unknown => chain,
      insertContentAt: (): unknown => chain,
      run: runSpy,
    };
    const editor = { chain: (): unknown => chain };

    const buildProps = (items: Array<MentionPickerCategoryRow>, query: string): SuggestionProps =>
      ({
        items,
        command: vi.fn(),
        query,
        editor,
        range: { from: 0, to: 1 },
        clientRect: null,
        decorationNode: null,
      }) as unknown as SuggestionProps;

    const ref = createRef<SuggestionListRef>();
    const { rerender } = render(
      <Wrapper>
        <MentionPickerList
          ref={ref}
          subConfigs={subConfigs}
          onTriggerImageUpload={vi.fn()}
          triggerChar="+"
          {...buildProps(allCategories, "")}
        />
      </Wrapper>,
    );

    pressKey(ref, "ArrowDown");
    pressKey(ref, "ArrowDown");

    rerender(
      <Wrapper>
        <MentionPickerList
          ref={ref}
          subConfigs={subConfigs}
          onTriggerImageUpload={vi.fn()}
          triggerChar="+"
          {...buildProps(ageCategories, "age")}
        />
      </Wrapper>,
    );

    pressKey(ref, "Tab");

    // With the selection-reset working, the chain fires the drill-in
    // (deleteRange + insertContentAt + run). Without it, the stale index
    // 2 sits past the end of the new list and Tab is a no-op.
    expect(runSpy).toHaveBeenCalled();
  });
});
