import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatActionsAtom } from "~/common/state/atoms/chatActions";
import type { SkillEntry } from "~/common/state/hooks/useSkills";
import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";

import { SkillsPanel } from "./SkillsPanel";

// `vi.mock` is hoisted to the top of the file, so the spy bindings have to
// live inside `vi.hoisted` to be available when the mock factories run.
const { mockUseSkills, mockUseTaskSupportsSkills } = vi.hoisted(() => ({
  mockUseSkills: vi.fn<() => { skills: ReadonlyArray<SkillEntry>; isLoading: boolean; error: string | null }>(),
  mockUseTaskSupportsSkills: vi.fn<() => boolean | undefined>(),
}));

// Mock the data hook so we can drive the panel from tests without an HTTP
// stub. The real hook is exercised separately in useSkills.test.ts.
vi.mock("~/common/state/hooks/useSkills", () => ({
  useSkills: (): { skills: ReadonlyArray<SkillEntry>; isLoading: boolean; error: string | null } => mockUseSkills(),
}));

// Mock the capability hook so a test can drive the skills gate directly.
vi.mock("~/common/state/hooks/useTaskHelpers", () => ({
  useTaskSupportsSkills: (): boolean | undefined => mockUseTaskSupportsSkills(),
}));

const customSkill = (overrides: Partial<SkillEntry> = {}): SkillEntry => ({
  name: "fix-bug",
  description: "Fix a bug using TDD",
  type: "custom",
  filePath: "/repo/.claude/skills/fix-bug/SKILL.md",
  ...overrides,
});

const builtinSkill = (overrides: Partial<SkillEntry> = {}): SkillEntry => ({
  name: "init",
  description: "Initialize a new CLAUDE.md",
  type: "builtin",
  filePath: null,
  ...overrides,
});

type RenderOpts = {
  skills?: ReadonlyArray<SkillEntry>;
  isLoading?: boolean;
  error?: string | null;
  insertSkill?: ((skill: { name: string; description: string; type: SkillEntry["type"] }) => void) | null;
  isChatDisabled?: boolean;
};

const renderSkillsPanel = (
  opts: RenderOpts = {},
): { store: ReturnType<typeof createStore>; insertSkill: ReturnType<typeof vi.fn> } => {
  const { skills = [], isLoading = false, error = null, insertSkill = vi.fn(), isChatDisabled = false } = opts;

  mockUseSkills.mockReturnValue({ skills, isLoading, error });

  const store = createStore();
  // The panel resolves its workspace from the section shell's active
  // workspace rather than the route.
  store.set(activeWorkspaceIdAtom, "test-workspace-id");
  store.set(chatActionsAtom, {
    appendText: vi.fn(),
    insertSkill,
    sendMessage: vi.fn().mockResolvedValue(undefined),
    isDisabled: isChatDisabled,
  });

  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );

  render(<SkillsPanel />, { wrapper: Wrapper });
  return { store, insertSkill: insertSkill as ReturnType<typeof vi.fn> };
};

beforeEach(() => {
  vi.clearAllMocks();
  // Default to a skills-supporting harness so the listing/search/insert tests
  // render the skills they pass in; the gated-off test overrides this.
  mockUseTaskSupportsSkills.mockReturnValue(true);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SkillsPanel — render states", () => {
  it("shows the loading message while skills are being fetched", () => {
    renderSkillsPanel({ isLoading: true });
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows the error message when the fetch failed", () => {
    renderSkillsPanel({ error: "Failed to load skills" });
    expect(screen.getByText("Failed to load skills")).toBeInTheDocument();
  });

  it("shows the no-skills empty state when the list is empty and no query", () => {
    renderSkillsPanel({ skills: [] });
    expect(screen.getByText("No skills found")).toBeInTheDocument();
    // Empty-state hint points the user at .claude/skills/.
    expect(screen.getByText((c) => c.includes(".claude/skills/"))).toBeInTheDocument();
  });

  it("collapses to the unavailable empty state when the harness does not support skills", () => {
    mockUseTaskSupportsSkills.mockReturnValue(false);
    renderSkillsPanel({ skills: [customSkill(), builtinSkill()] });
    expect(document.querySelectorAll('[data-testid="SKILL_CHIP"]')).toHaveLength(0);
    expect(screen.getByText("Skills unavailable")).toBeInTheDocument();
    expect(screen.getByText("This harness does not support skills.")).toBeInTheDocument();
  });

  it("shows the no-matches empty state when search filters everything out", () => {
    renderSkillsPanel({ skills: [customSkill()] });
    fireEvent.click(screen.getByLabelText(/Search skills/i));
    fireEvent.change(screen.getByPlaceholderText("Search skills..."), {
      target: { value: "no-match-anywhere" },
    });
    expect(screen.getByText("No matching skills")).toBeInTheDocument();
  });
});

describe("SkillsPanel — listing", () => {
  it("renders each skill with its name", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "fix-bug" }), builtinSkill({ name: "init" })],
    });
    expect(screen.getByText("fix-bug")).toBeInTheDocument();
    expect(screen.getByText("init")).toBeInTheDocument();
  });
});

describe("SkillsPanel — type-grouped sections", () => {
  // Pulls every visible skill row in DOM order. Useful for asserting the
  // group-then-alphabetical sort lays out chips the way users expect.
  const visibleSkillNames = (): Array<string> =>
    Array.from(document.querySelectorAll<HTMLElement>('[data-testid="SKILL_CHIP"]'))
      .map((el) => el.getAttribute("data-skill-name"))
      .filter((name): name is string => name !== null);

  it("renders a section header for each represented type", () => {
    renderSkillsPanel({
      skills: [
        customSkill({ name: "my-skill" }),
        { name: "sculptor:fix-bug", description: "plugin", type: "sculptor", filePath: "/p" },
        builtinSkill({ name: "loop" }),
      ],
    });
    expect(screen.getByText("Custom Skills")).toBeInTheDocument();
    expect(screen.getByText("Sculptor")).toBeInTheDocument();
    expect(screen.getByText("Built-in")).toBeInTheDocument();
  });

  it("orders groups custom → sculptor → builtin and alpha-sorts within each", () => {
    renderSkillsPanel({
      skills: [
        // Mix the input order so the test proves the panel does the sort,
        // not the input array.
        builtinSkill({ name: "loop" }),
        customSkill({ name: "zeta-skill" }),
        { name: "sculptor:fix-bug", description: "plugin", type: "sculptor", filePath: "/p" },
        customSkill({ name: "alpha-skill" }),
        builtinSkill({ name: "batch" }),
      ],
    });
    expect(visibleSkillNames()).toEqual(["alpha-skill", "zeta-skill", "sculptor:fix-bug", "batch", "loop"]);
  });

  it("hides a section header when its group has no visible skills", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), builtinSkill({ name: "loop" })],
    });
    fireEvent.click(screen.getByLabelText(/Search skills/i));
    fireEvent.change(screen.getByPlaceholderText("Search skills..."), { target: { value: "alpha" } });
    // Only the Custom group has a match — Built-in's header disappears.
    expect(screen.getByText("Custom Skills")).toBeInTheDocument();
    expect(screen.queryByText("Built-in")).not.toBeInTheDocument();
  });
});

describe("SkillsPanel — collapsible sections", () => {
  const visibleSkillNames = (): Array<string> =>
    Array.from(document.querySelectorAll<HTMLElement>('[data-testid="SKILL_CHIP"]'))
      .map((el) => el.getAttribute("data-skill-name"))
      .filter((name): name is string => name !== null);

  it("clicking a header collapses the chips of that group, keeping the header visible", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), builtinSkill({ name: "loop" })],
    });
    expect(visibleSkillNames()).toEqual(["alpha", "loop"]);
    fireEvent.click(screen.getByText("Built-in"));
    // The Built-in section is now collapsed — its chip is gone, header stays.
    expect(visibleSkillNames()).toEqual(["alpha"]);
    expect(screen.getByText("Built-in")).toBeInTheDocument();
  });

  it("clicking a collapsed header expands it again", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), builtinSkill({ name: "loop" })],
    });
    fireEvent.click(screen.getByText("Built-in"));
    expect(visibleSkillNames()).toEqual(["alpha"]);
    fireEvent.click(screen.getByText("Built-in"));
    expect(visibleSkillNames()).toEqual(["alpha", "loop"]);
  });

  it("aria-expanded reflects the collapse state on the header", () => {
    renderSkillsPanel({ skills: [customSkill({ name: "alpha" })] });
    const header = screen.getByText("Custom Skills").closest('[role="button"]');
    expect(header).not.toBeNull();
    expect(header).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(header!);
    expect(header).toHaveAttribute("aria-expanded", "false");
  });

  it("Enter and Space on the focused header toggle the collapse state", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), builtinSkill({ name: "loop" })],
    });
    const header = screen.getByText("Built-in").closest('[role="button"]') as HTMLElement;
    fireEvent.keyDown(header, { key: "Enter" });
    expect(header).toHaveAttribute("aria-expanded", "false");
    fireEvent.keyDown(header, { key: " " });
    expect(header).toHaveAttribute("aria-expanded", "true");
  });

  it("keyboard navigation skips chips in collapsed groups", () => {
    // Selection is over `visibleSkills`, so collapsing "Built-in" must
    // remove `loop` from the navigation order — ArrowDown from the only
    // visible row stays put.
    const insertSkill = vi.fn();
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), builtinSkill({ name: "loop" })],
      insertSkill,
    });
    // Collapse the Built-in section, then start a search.
    fireEvent.click(screen.getByText("Built-in"));
    fireEvent.click(screen.getByLabelText(/Search skills/i));
    const input = screen.getByPlaceholderText("Search skills...");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    // Only `alpha` is reachable — `loop` is hidden.
    expect(insertSkill).toHaveBeenCalledTimes(1);
    expect(insertSkill).toHaveBeenCalledWith({
      name: "alpha",
      description: expect.any(String),
      type: "custom",
    });
  });
});

describe("SkillsPanel — search", () => {
  const openSearch = (): void => {
    fireEvent.click(screen.getByLabelText(/Search skills/i));
  };

  const typeQuery = (q: string): void => {
    fireEvent.change(screen.getByPlaceholderText("Search skills..."), { target: { value: q } });
  };

  it("filters by name (case-insensitive substring)", () => {
    renderSkillsPanel({
      skills: [
        customSkill({ name: "fix-bug", description: "alpha" }),
        customSkill({ name: "review", description: "beta" }),
      ],
    });
    openSearch();
    typeQuery("FIX");
    expect(screen.getByText("fix-bug")).toBeInTheDocument();
    expect(screen.queryByText("review")).not.toBeInTheDocument();
  });

  it("filters by description as well as name", () => {
    renderSkillsPanel({
      skills: [
        customSkill({ name: "alpha", description: "matches description only" }),
        customSkill({ name: "beta", description: "unrelated" }),
      ],
    });
    openSearch();
    typeQuery("description only");
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.queryByText("beta")).not.toBeInTheDocument();
  });
});

describe("SkillsPanel — click-to-insert", () => {
  it("calls insertSkill with the skill's name/description/type when a chip is clicked", () => {
    const insertSkill = vi.fn();
    renderSkillsPanel({
      skills: [customSkill({ name: "fix-bug", description: "Fix a bug", type: "custom" })],
      insertSkill,
    });
    fireEvent.click(screen.getByText("fix-bug"));
    expect(insertSkill).toHaveBeenCalledWith({
      name: "fix-bug",
      description: "Fix a bug",
      type: "custom",
    });
  });

  it("safely no-ops when insertSkill is null (chat hasn't mounted yet)", () => {
    // Regression: the panel can render before useChatData wires the atom.
    // Clicking a chip in that window must not throw.
    renderSkillsPanel({
      skills: [customSkill()],
      insertSkill: null,
    });
    expect(() => fireEvent.click(screen.getByText("fix-bug"))).not.toThrow();
  });
});

describe("SkillsPanel — action buttons", () => {
  it("renders the Open-in-Sculptor button for non-builtin skills", () => {
    renderSkillsPanel({ skills: [customSkill()] });
    expect(screen.getByLabelText(/Open in Sculptor/i)).toBeInTheDocument();
  });

  it("does NOT render an action button for builtin skills", () => {
    // Builtins have filePath: null and no on-disk source to open.
    renderSkillsPanel({ skills: [builtinSkill()] });
    expect(screen.queryByLabelText(/Open in Sculptor/i)).not.toBeInTheDocument();
  });

  it("does not fire the row's insertSkill when the action button is clicked", () => {
    // SkillChip's action button uses stopPropagation. Without it, opening
    // the file would also insert the skill — a UX bug.
    const insertSkill = vi.fn();
    renderSkillsPanel({ skills: [customSkill()], insertSkill });
    fireEvent.click(screen.getByLabelText(/Open in Sculptor/i));
    expect(insertSkill).not.toHaveBeenCalled();
  });
});

describe("SkillsPanel — popover dismiss-on-filter regression", () => {
  // Regression test for the bug fixed in this branch: hovering a chip and then
  // typing a query that filters that chip out left the popover stranded with
  // `activeChipElementRef` pointing at a detached node. After the fix, any
  // change to the visible list dismisses the popover.

  const advancePopoverOpen = (): void => {
    // OPEN_DELAY_MS is 420ms in the panel; round up. The setTimeout
    // callback calls setState, so wrap in act so React flushes the
    // resulting render before we assert.
    act(() => {
      vi.advanceTimersByTime(500);
    });
  };

  it("hovering a chip eventually opens the popover (sanity check)", () => {
    vi.useFakeTimers();
    try {
      renderSkillsPanel({
        skills: [customSkill({ name: "fix-bug", description: "POPOVER_DESCRIPTION_PROBE" })],
      });
      const chip = screen.getByText("fix-bug");
      fireEvent.mouseEnter(chip);
      advancePopoverOpen();
      // The popover renders SkillHoverContent which echoes the description.
      // The chip itself never renders the description, so finding the
      // description text means the popover is on screen.
      expect(screen.getByText("POPOVER_DESCRIPTION_PROBE")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("dismisses the popover when a search query filters the active chip out", () => {
    vi.useFakeTimers();
    try {
      renderSkillsPanel({
        skills: [
          customSkill({ name: "fix-bug", description: "POPOVER_DESCRIPTION_PROBE" }),
          customSkill({ name: "review", description: "review desc" }),
        ],
      });
      // Hover the first chip and let the popover open.
      const chip = screen.getByText("fix-bug");
      fireEvent.mouseEnter(chip);
      advancePopoverOpen();
      expect(screen.getByText("POPOVER_DESCRIPTION_PROBE")).toBeInTheDocument();

      // Open search and type a query that matches "review" only — fix-bug
      // (and its open popover) should disappear from the DOM.
      fireEvent.click(screen.getByLabelText(/Search skills/i));
      fireEvent.change(screen.getByPlaceholderText("Search skills..."), {
        target: { value: "review" },
      });

      expect(screen.queryByText("fix-bug")).not.toBeInTheDocument();
      // Popover has been dismissed; its content must not still be in the DOM.
      expect(screen.queryByText("POPOVER_DESCRIPTION_PROBE")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("SkillsPanel — popover collision-aware side", () => {
  // Regression: the hover popover was hardcoded to sit to the LEFT of the
  // chip column. In a narrow left-docked panel there is no room on the left,
  // so it slid off-screen. The popover must flip to the side with space.
  const advancePopoverOpen = (): void => {
    act(() => {
      vi.advanceTimersByTime(500);
    });
  };

  // Stub a chip's layout box so the side computation has a real `left` to
  // reason about (jsdom returns an all-zero rect otherwise).
  const stubChipRect = (chip: HTMLElement, left: number): void => {
    chip.getBoundingClientRect = (): DOMRect =>
      ({ left, right: left + 100, top: 100, bottom: 130, width: 100, height: 30, x: left, y: 100 }) as DOMRect;
  };

  const popoverSide = (): string | null => {
    const hitArea = document.querySelector<HTMLElement>("[data-skill-popover]");
    return hitArea?.getAttribute("data-side") ?? null;
  };

  it("flips the popover to the right when the chip hugs the left edge (no room on the left)", () => {
    vi.useFakeTimers();
    try {
      renderSkillsPanel({
        skills: [customSkill({ name: "fix-bug", description: "POPOVER_DESCRIPTION_PROBE" })],
      });
      const chip = screen.getByText("fix-bug").closest('[data-testid="SKILL_CHIP"]') as HTMLElement;
      // Chip's left edge is only 20px from the viewport edge — a ~300px
      // popover cannot fit on the left, so it must flip to the right.
      stubChipRect(chip, 20);
      fireEvent.mouseEnter(chip);
      advancePopoverOpen();
      expect(screen.getByText("POPOVER_DESCRIPTION_PROBE")).toBeInTheDocument();
      expect(popoverSide()).toBe("right");
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps the popover on the left when the chip has room to its left", () => {
    vi.useFakeTimers();
    try {
      renderSkillsPanel({
        skills: [customSkill({ name: "fix-bug", description: "POPOVER_DESCRIPTION_PROBE" })],
      });
      const chip = screen.getByText("fix-bug").closest('[data-testid="SKILL_CHIP"]') as HTMLElement;
      // Chip sits far from the left edge (600px), leaving plenty of room for
      // the popover on the left — the default side is preserved.
      stubChipRect(chip, 600);
      fireEvent.mouseEnter(chip);
      advancePopoverOpen();
      expect(screen.getByText("POPOVER_DESCRIPTION_PROBE")).toBeInTheDocument();
      expect(popoverSide()).toBe("left");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("SkillsPanel — keyboard navigation in search", () => {
  // Helpers — selection state lives on the chip via `data-selected`. The
  // input owns focus the whole time, so arrow / enter keys fire on it.
  const openSearch = (): void => {
    fireEvent.click(screen.getByLabelText(/Search skills/i));
  };
  const searchInput = (): HTMLElement => screen.getByPlaceholderText("Search skills...");
  const selectedSkillName = (): string | null => {
    const chip = document.querySelector<HTMLElement>('[data-testid="SKILL_CHIP"][data-selected="true"]');
    return chip?.getAttribute("data-skill-name") ?? null;
  };

  it("selects the first chip when search opens", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), customSkill({ name: "beta" })],
    });
    openSearch();
    expect(selectedSkillName()).toBe("alpha");
  });

  it("ArrowDown advances the selection to the next chip", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), customSkill({ name: "beta" })],
    });
    openSearch();
    fireEvent.keyDown(searchInput(), { key: "ArrowDown" });
    expect(selectedSkillName()).toBe("beta");
  });

  it("ArrowUp moves the selection to the previous chip", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), customSkill({ name: "beta" })],
    });
    openSearch();
    fireEvent.keyDown(searchInput(), { key: "ArrowDown" });
    fireEvent.keyDown(searchInput(), { key: "ArrowUp" });
    expect(selectedSkillName()).toBe("alpha");
  });

  it("ArrowDown at the last chip stays put (no wrap)", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), customSkill({ name: "beta" })],
    });
    openSearch();
    fireEvent.keyDown(searchInput(), { key: "ArrowDown" });
    fireEvent.keyDown(searchInput(), { key: "ArrowDown" });
    fireEvent.keyDown(searchInput(), { key: "ArrowDown" });
    expect(selectedSkillName()).toBe("beta");
  });

  it("ArrowUp at the first chip stays put (no wrap)", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), customSkill({ name: "beta" })],
    });
    openSearch();
    fireEvent.keyDown(searchInput(), { key: "ArrowUp" });
    fireEvent.keyDown(searchInput(), { key: "ArrowUp" });
    expect(selectedSkillName()).toBe("alpha");
  });

  it("Enter inserts the currently-selected chip", () => {
    const insertSkill = vi.fn();
    renderSkillsPanel({
      skills: [
        customSkill({ name: "alpha", description: "A desc", type: "custom" }),
        customSkill({ name: "beta", description: "B desc", type: "custom" }),
      ],
      insertSkill,
    });
    openSearch();
    fireEvent.keyDown(searchInput(), { key: "ArrowDown" });
    fireEvent.keyDown(searchInput(), { key: "Enter" });
    expect(insertSkill).toHaveBeenCalledWith({ name: "beta", description: "B desc", type: "custom" });
  });

  it("typing a query resets the selection back to the first match", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), customSkill({ name: "beta" }), customSkill({ name: "gamma" })],
    });
    openSearch();
    fireEvent.keyDown(searchInput(), { key: "ArrowDown" });
    fireEvent.keyDown(searchInput(), { key: "ArrowDown" });
    expect(selectedSkillName()).toBe("gamma");
    // Typing narrows the list — selection must snap back to the new top match.
    fireEvent.change(searchInput(), { target: { value: "be" } });
    expect(selectedSkillName()).toBe("beta");
  });

  it("Enter is a no-op when the filtered list is empty", () => {
    const insertSkill = vi.fn();
    renderSkillsPanel({ skills: [customSkill({ name: "alpha" })], insertSkill });
    openSearch();
    fireEvent.change(searchInput(), { target: { value: "no-match" } });
    fireEvent.keyDown(searchInput(), { key: "Enter" });
    expect(insertSkill).not.toHaveBeenCalled();
  });

  it("Enter does not insert when chat is disabled", () => {
    // Mirrors the click path: a queued chat must not silently trigger an
    // insert from a keyboard activation either.
    const insertSkill = vi.fn();
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" })],
      insertSkill,
      isChatDisabled: true,
    });
    openSearch();
    fireEvent.keyDown(searchInput(), { key: "Enter" });
    expect(insertSkill).not.toHaveBeenCalled();
  });

  it("no chip is marked selected when search is closed", () => {
    renderSkillsPanel({
      skills: [customSkill({ name: "alpha" }), customSkill({ name: "beta" })],
    });
    // Search header isn't open — the panel header is showing instead.
    expect(selectedSkillName()).toBeNull();
  });
});
