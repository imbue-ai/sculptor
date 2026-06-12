import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SkillEntry } from "~/common/state/hooks/useSkills";

import { SkillChip } from "./SkillChip";

const skill = (overrides: Partial<SkillEntry> = {}): SkillEntry => ({
  name: "fix-bug",
  description: "Fix a bug using TDD",
  type: "custom",
  filePath: "/repo/.claude/skills/fix-bug/SKILL.md",
  ...overrides,
});

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

afterEach(() => {
  cleanup();
});

describe("SkillChip — primary action", () => {
  it("renders the skill name with a leading slash", () => {
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={vi.fn()} />
      </Wrapper>,
    );
    expect(screen.getByText("fix-bug")).toBeInTheDocument();
    expect(screen.getByText("/")).toBeInTheDocument();
  });

  it("calls onClick when the row is clicked", () => {
    const onClick = vi.fn();
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={onClick} />
      </Wrapper>,
    );
    fireEvent.click(screen.getByRole("button", { name: /fix-bug/ }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("activates on Enter and Space keys", () => {
    const onClick = vi.fn();
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={onClick} />
      </Wrapper>,
    );
    const row = screen.getByRole("button", { name: /fix-bug/ });
    fireEvent.keyDown(row, { key: "Enter" });
    fireEvent.keyDown(row, { key: " " });
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it("does NOT call onClick on other keys", () => {
    const onClick = vi.fn();
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={onClick} />
      </Wrapper>,
    );
    fireEvent.keyDown(screen.getByRole("button", { name: /fix-bug/ }), { key: "a" });
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("SkillChip — disabled state", () => {
  it("does not call onClick when disabled", () => {
    const onClick = vi.fn();
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={onClick} disabled />
      </Wrapper>,
    );
    fireEvent.click(screen.getByRole("button", { name: /fix-bug/ }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("does not activate on Enter when disabled", () => {
    const onClick = vi.fn();
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={onClick} disabled />
      </Wrapper>,
    );
    fireEvent.keyDown(screen.getByRole("button", { name: /fix-bug/ }), { key: "Enter" });
    expect(onClick).not.toHaveBeenCalled();
  });

  it("removes the row from the tab order when disabled", () => {
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={vi.fn()} disabled />
      </Wrapper>,
    );
    expect(screen.getByRole("button", { name: /fix-bug/ })).toHaveAttribute("tabindex", "-1");
  });

  it("sets aria-disabled when disabled", () => {
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={vi.fn()} disabled />
      </Wrapper>,
    );
    expect(screen.getByRole("button", { name: /fix-bug/ })).toHaveAttribute("aria-disabled", "true");
  });
});

describe("SkillChip — action buttons", () => {
  it("renders Open-in-Sculptor when onOpenInSculptor is provided", () => {
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={vi.fn()} onOpenInSculptor={vi.fn()} />
      </Wrapper>,
    );
    expect(screen.getByLabelText("Open in Sculptor")).toBeInTheDocument();
  });

  it("renders no action button for built-in skills (no callback provided)", () => {
    render(
      <Wrapper>
        <SkillChip skill={skill({ type: "builtin", filePath: null })} onClick={vi.fn()} />
      </Wrapper>,
    );
    expect(screen.queryByLabelText("Open in Sculptor")).not.toBeInTheDocument();
  });

  it("Open-in-Sculptor stops propagation so the row's onClick does NOT fire", () => {
    // Without stopPropagation, clicking the icon would both open the file
    // AND insert the skill into chat — a confusing UX bug.
    const rowOnClick = vi.fn();
    const openInSculptor = vi.fn();
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={rowOnClick} onOpenInSculptor={openInSculptor} />
      </Wrapper>,
    );
    fireEvent.click(screen.getByLabelText("Open in Sculptor"));
    expect(openInSculptor).toHaveBeenCalledTimes(1);
    expect(rowOnClick).not.toHaveBeenCalled();
  });
});

describe("SkillChip — hover handlers", () => {
  it("forwards mouseenter / mouseleave events to the panel", () => {
    const onMouseEnter = vi.fn();
    const onMouseLeave = vi.fn();
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={vi.fn()} onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave} />
      </Wrapper>,
    );
    const row = screen.getByRole("button", { name: /fix-bug/ });
    fireEvent.mouseEnter(row);
    fireEvent.mouseLeave(row);
    expect(onMouseEnter).toHaveBeenCalledTimes(1);
    expect(onMouseLeave).toHaveBeenCalledTimes(1);
  });
});

describe("SkillChip — selected state", () => {
  it("exposes data-selected and aria-selected when selected", () => {
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={vi.fn()} selected />
      </Wrapper>,
    );
    const row = screen.getByRole("button", { name: /fix-bug/ });
    expect(row).toHaveAttribute("data-selected", "true");
    expect(row).toHaveAttribute("aria-selected", "true");
  });

  it("omits data-selected and aria-selected when not selected", () => {
    render(
      <Wrapper>
        <SkillChip skill={skill()} onClick={vi.fn()} />
      </Wrapper>,
    );
    const row = screen.getByRole("button", { name: /fix-bug/ });
    expect(row).not.toHaveAttribute("data-selected");
    expect(row).not.toHaveAttribute("aria-selected");
  });
});
