import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SkillsSearch } from "./SkillsSearch";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

afterEach(() => {
  cleanup();
});

describe("SkillsSearch", () => {
  it("auto-focuses the input on mount", () => {
    render(
      <Wrapper>
        <SkillsSearch query="" onQueryChange={vi.fn()} onClose={vi.fn()} />
      </Wrapper>,
    );
    expect(screen.getByPlaceholderText("Search skills...")).toHaveFocus();
  });

  it("calls onQueryChange when the user types", () => {
    const onQueryChange = vi.fn();
    render(
      <Wrapper>
        <SkillsSearch query="" onQueryChange={onQueryChange} onClose={vi.fn()} />
      </Wrapper>,
    );
    fireEvent.change(screen.getByPlaceholderText("Search skills..."), { target: { value: "fix" } });
    expect(onQueryChange).toHaveBeenCalledWith("fix");
  });

  it("calls onClose when the user presses Escape", () => {
    const onClose = vi.fn();
    render(
      <Wrapper>
        <SkillsSearch query="some query" onQueryChange={vi.fn()} onClose={onClose} />
      </Wrapper>,
    );
    fireEvent.keyDown(screen.getByPlaceholderText("Search skills..."), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    render(
      <Wrapper>
        <SkillsSearch query="" onQueryChange={vi.fn()} onClose={onClose} />
      </Wrapper>,
    );
    // The close button is the only visible button in the search header.
    fireEvent.click(screen.getAllByRole("button")[0]);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("reflects the controlled query prop in the input", () => {
    render(
      <Wrapper>
        <SkillsSearch query="alpha" onQueryChange={vi.fn()} onClose={vi.fn()} />
      </Wrapper>,
    );
    expect(screen.getByPlaceholderText("Search skills...")).toHaveValue("alpha");
  });

  it("calls onArrowDown when ArrowDown is pressed", () => {
    const onArrowDown = vi.fn();
    render(
      <Wrapper>
        <SkillsSearch query="" onQueryChange={vi.fn()} onClose={vi.fn()} onArrowDown={onArrowDown} />
      </Wrapper>,
    );
    fireEvent.keyDown(screen.getByPlaceholderText("Search skills..."), { key: "ArrowDown" });
    expect(onArrowDown).toHaveBeenCalledTimes(1);
  });

  it("calls onArrowUp when ArrowUp is pressed", () => {
    const onArrowUp = vi.fn();
    render(
      <Wrapper>
        <SkillsSearch query="" onQueryChange={vi.fn()} onClose={vi.fn()} onArrowUp={onArrowUp} />
      </Wrapper>,
    );
    fireEvent.keyDown(screen.getByPlaceholderText("Search skills..."), { key: "ArrowUp" });
    expect(onArrowUp).toHaveBeenCalledTimes(1);
  });

  it("calls onEnter when Enter is pressed", () => {
    const onEnter = vi.fn();
    render(
      <Wrapper>
        <SkillsSearch query="" onQueryChange={vi.fn()} onClose={vi.fn()} onEnter={onEnter} />
      </Wrapper>,
    );
    fireEvent.keyDown(screen.getByPlaceholderText("Search skills..."), { key: "Enter" });
    expect(onEnter).toHaveBeenCalledTimes(1);
  });

  it("does not throw when arrow / enter handlers are not provided", () => {
    render(
      <Wrapper>
        <SkillsSearch query="" onQueryChange={vi.fn()} onClose={vi.fn()} />
      </Wrapper>,
    );
    const input = screen.getByPlaceholderText("Search skills...");
    expect(() => {
      fireEvent.keyDown(input, { key: "ArrowDown" });
      fireEvent.keyDown(input, { key: "ArrowUp" });
      fireEvent.keyDown(input, { key: "Enter" });
    }).not.toThrow();
  });
});
