import { cleanup, fireEvent, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { JjPromptSettingRow } from "./JjPromptSettingRow.tsx";

const GIT_PROMPT = "Stage every changed file, then commit.";
const SUGGESTED_PROMPT = "Describe the working copy, then start a new change.";

const renderRow = (value: string | null, onSave = vi.fn()): ReturnType<typeof vi.fn> => {
  renderWithProviders(
    <JjPromptSettingRow
      title="jj commit prompt"
      description="Sent instead of the commit prompt."
      value={value}
      gitPrompt={GIT_PROMPT}
      suggestedPrompt={SUGGESTED_PROMPT}
      onSave={onSave}
      data-testid="row"
    />,
    { store: createStore() },
  );
  return onSave;
};

afterEach(() => {
  cleanup();
});

describe("JjPromptSettingRow", () => {
  it("shows the git prompt it falls back to while unset, and offers the suggested wording", () => {
    const onSave = renderRow(null);

    expect(screen.getByText(GIT_PROMPT)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use suggested wording" }));

    expect(onSave).toHaveBeenCalledWith(SUGGESTED_PROMPT);
  });

  it("saves an edited jj prompt when the field loses focus", () => {
    const onSave = renderRow("Commit with jj");

    const field = screen.getByRole("textbox");
    expect(field).toHaveValue("Commit with jj");
    fireEvent.change(field, { target: { value: "Describe and commit with jj" } });
    fireEvent.blur(field);

    expect(onSave).toHaveBeenCalledWith("Describe and commit with jj");
  });

  it("goes back to the git prompt when asked, or when the jj prompt is cleared", () => {
    const onSave = renderRow("Commit with jj");

    fireEvent.click(screen.getByRole("button", { name: "Use the git prompt" }));
    const field = screen.getByRole("textbox");
    fireEvent.change(field, { target: { value: "   " } });
    fireEvent.blur(field);

    expect(onSave.mock.calls).toEqual([[null], [null]]);
  });

  it("saves nothing when the field loses focus unchanged", () => {
    const onSave = renderRow("Commit with jj");

    fireEvent.blur(screen.getByRole("textbox"));

    expect(onSave).not.toHaveBeenCalled();
  });
});
