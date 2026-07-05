import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import type { SuggestionProps } from "@tiptap/suggestion";
import type { ReactElement, ReactNode } from "react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { badgeLabelForType } from "../../common/utils/skillBadge";
import { SkillList } from "./SkillList";
import type { SuggestionListRef } from "./SuggestionListContainer";

// Same rationale as SuggestionListContainer.test.tsx — bypass the
// react-virtual measurement path so every item renders in jsdom.
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }): unknown => ({
    getVirtualItems: (): Array<{ index: number; start: number; size: number; key: number }> =>
      Array.from({ length: count }, (_, i) => ({ index: i, start: i * 26, size: 26, key: i })),
    getTotalSize: (): number => count * 26,
    scrollToIndex: (): void => {},
  }),
}));

afterEach(() => {
  cleanup();
});

type SkillItemShape = {
  id: string;
  label: string;
  description?: string;
  skillType?: "builtin" | "custom" | "sculptor";
};

const makeSkillProps = (items: Array<SkillItemShape>, query = ""): SuggestionProps =>
  ({
    items,
    command: vi.fn(),
    query,
    editor: {} as unknown,
    range: { from: 0, to: 0 },
    clientRect: null,
    decorationNode: null,
  }) as unknown as SuggestionProps;

const renderSkillList = (
  props: SuggestionProps,
): { ref: React.RefObject<SuggestionListRef | null>; container: HTMLElement } => {
  const ref = createRef<SuggestionListRef>();
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;
  const { container } = render(
    <Wrapper>
      <SkillList ref={ref} {...props} />
    </Wrapper>,
  );
  return { ref, container };
};

describe("SkillList — row rendering", () => {
  it("renders every item as a /-prefixed label", () => {
    const items: Array<SkillItemShape> = [
      { id: "/foo", label: "foo", description: "Foo skill", skillType: "custom" },
      { id: "/bar", label: "bar", description: "Bar skill", skillType: "builtin" },
    ];
    renderSkillList(makeSkillProps(items));
    // Row labels are prefixed with "/" in the list; the detail pane also
    // echoes the /name of the active item, so the active row's label appears
    // twice in the DOM.
    expect(screen.getAllByText((content) => content === "/foo").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText((content) => content === "/bar").length).toBeGreaterThanOrEqual(1);
  });

  it("shows an empty state when there are no items", () => {
    renderSkillList(makeSkillProps([]));
    expect(screen.getByText("No matching skills")).toBeTruthy();
    // Hint points the user at where to add skills.
    expect(screen.getByText((content) => content.includes(".claude/skills/"))).toBeTruthy();
  });
});

describe("SkillList — detail pane", () => {
  it("shows description and /name for the first item by default", () => {
    const items: Array<SkillItemShape> = [
      { id: "/first", label: "first", description: "First description", skillType: "custom" },
      { id: "/second", label: "second", description: "Second description", skillType: "custom" },
    ];
    renderSkillList(makeSkillProps(items));
    // The detail pane is a separate pane from the list rows; description is
    // only rendered there.
    expect(screen.getByText("First description")).toBeTruthy();
    // The /name also renders in the detail title.
    const matches = screen.getAllByText((content) => content === "/first");
    // One in the row, one in the detail title.
    expect(matches.length).toBeGreaterThanOrEqual(2);
  });

  it("renders a 'built-in' badge for builtin skills", () => {
    const items: Array<SkillItemShape> = [
      { id: "/help", label: "help", description: "Built-in help", skillType: "builtin" },
    ];
    renderSkillList(makeSkillProps(items));
    expect(screen.getByText(badgeLabelForType("builtin"))).toBeTruthy();
    expect(screen.getByText("Built-in help")).toBeTruthy();
  });

  it("renders a 'Sculptor' badge for plugin skills", () => {
    const items: Array<SkillItemShape> = [
      { id: "/sculptor:fix-bug", label: "sculptor:fix-bug", description: "Fix a bug", skillType: "sculptor" },
    ];
    renderSkillList(makeSkillProps(items));
    expect(screen.getByText(badgeLabelForType("sculptor"))).toBeTruthy();
  });

  it("renders a 'custom' badge for custom skills", () => {
    const items: Array<SkillItemShape> = [
      { id: "/my-skill", label: "my-skill", description: "A custom one", skillType: "custom" },
    ];
    renderSkillList(makeSkillProps(items));
    expect(screen.getByText(badgeLabelForType("custom"))).toBeTruthy();
  });

  it("omits the description block when a skill has no description", () => {
    const items: Array<SkillItemShape> = [{ id: "/bare", label: "bare", skillType: "custom" }];
    const { container } = renderSkillList(makeSkillProps(items));
    // No description text anywhere — the detailDescription element is gated
    // on presence of the description field.
    expect(container.textContent).not.toContain("undefined");
  });
});

describe("SkillList — query highlighting", () => {
  it("wraps the matching substring in the row label with a highlight span", () => {
    const items: Array<SkillItemShape> = [{ id: "/persist-reload", label: "persist-reload", skillType: "custom" }];
    const { container } = renderSkillList(makeSkillProps(items, "reload"));
    // highlightMatch splits "persist-reload" into "persist-" + "reload" and
    // wraps the match in a span.highlight.
    const highlights = container.querySelectorAll(".highlight");
    expect(highlights.length).toBeGreaterThanOrEqual(1);
    // At least one highlight exactly matches the query text.
    expect(Array.from(highlights).some((el) => el.textContent === "reload")).toBe(true);
  });

  it("does not add a highlight span when there is no query", () => {
    const items: Array<SkillItemShape> = [{ id: "/foo", label: "foo", skillType: "custom" }];
    const { container } = renderSkillList(makeSkillProps(items, ""));
    expect(container.querySelector(".highlight")).toBeNull();
  });

  it("leaves the label untouched when the query does not match", () => {
    const items: Array<SkillItemShape> = [{ id: "/foo", label: "foo", skillType: "custom" }];
    const { container } = renderSkillList(makeSkillProps(items, "zzz"));
    expect(container.querySelector(".highlight")).toBeNull();
  });
});

describe("SkillList — keyboard committing via the shared container ref", () => {
  it("Enter commits the currently selected skill item", () => {
    // Assert the container delegation: SkillList hands its ref through to
    // SuggestionListContainer, so callers get the same onKeyDown contract.
    const command = vi.fn();
    const items: Array<SkillItemShape> = [
      { id: "/a", label: "a", skillType: "custom" },
      { id: "/b", label: "b", skillType: "custom" },
    ];
    const props = {
      items,
      command,
      query: "",
      editor: {} as unknown,
      range: { from: 0, to: 0 },
      clientRect: null,
      decorationNode: null,
    } as unknown as SuggestionProps;

    const { ref } = renderSkillList(props);
    const event = { key: "Enter", shiftKey: false } as unknown as KeyboardEvent;
    expect(ref.current!.onKeyDown({ event })).toBe(true);
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ id: "/a" }));
  });
});
