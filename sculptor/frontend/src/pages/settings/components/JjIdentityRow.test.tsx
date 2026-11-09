import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { JjIdentity, JjReadiness } from "~/api";
import { ElementIds } from "~/api";

import { JjIdentityRow } from "./JjIdentityRow.tsx";

afterEach(() => {
  cleanup();
});

const renderRow = (readiness: JjReadiness, onSave: (identity: JjIdentity) => Promise<void>): ReactElement => (
  <Theme>
    <JjIdentityRow readiness={readiness} onSave={onSave} />
  </Theme>
);

const inputValue = (testId: string): string => (screen.getByTestId(testId) as HTMLInputElement).value;

describe("JjIdentityRow", () => {
  it("shows a configured identity read-only", () => {
    render(renderRow({ blocker: null, identity: { name: "Ada Lovelace", email: "ada@example.com" } }, vi.fn()));

    expect(screen.getByTestId(ElementIds.JJ_IDENTITY).textContent).toContain("Ada Lovelace <ada@example.com>");
    expect(screen.queryByTestId(ElementIds.JJ_IDENTITY_FORM)).toBeNull();
  });

  it("offers a form prefilled with the suggested identity when jj has none", () => {
    render(
      renderRow(
        { blocker: "NO_IDENTITY", suggestedIdentity: { name: "Grace Hopper", email: "grace@example.com" } },
        vi.fn(),
      ),
    );

    expect(inputValue(ElementIds.JJ_IDENTITY_NAME_INPUT)).toBe("Grace Hopper");
    expect(inputValue(ElementIds.JJ_IDENTITY_EMAIL_INPUT)).toBe("grace@example.com");
  });

  it("saves the edited identity", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(renderRow({ blocker: "NO_IDENTITY", suggestedIdentity: { name: "", email: "" } }, onSave));

    fireEvent.change(screen.getByTestId(ElementIds.JJ_IDENTITY_NAME_INPUT), { target: { value: "Grace Hopper" } });
    fireEvent.change(screen.getByTestId(ElementIds.JJ_IDENTITY_EMAIL_INPUT), {
      target: { value: "grace@example.com" },
    });
    fireEvent.click(screen.getByTestId(ElementIds.JJ_IDENTITY_SUBMIT));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ name: "Grace Hopper", email: "grace@example.com" }));
  });

  it("keeps the save disabled until both halves are filled", () => {
    render(renderRow({ blocker: "NO_IDENTITY", suggestedIdentity: { name: "Grace Hopper", email: "" } }, vi.fn()));

    expect((screen.getByTestId(ElementIds.JJ_IDENTITY_SUBMIT) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows why a save failed", async () => {
    const onSave = vi.fn().mockRejectedValue(new Error("jj is not installed"));
    render(
      renderRow({ blocker: "NO_IDENTITY", suggestedIdentity: { name: "Grace", email: "grace@example.com" } }, onSave),
    );

    fireEvent.click(screen.getByTestId(ElementIds.JJ_IDENTITY_SUBMIT));

    expect(await screen.findByText("jj is not installed")).toBeTruthy();
  });

  it("explains that the identity is read once jj runs", () => {
    render(renderRow({ blocker: "NOT_INSTALLED" }, vi.fn()));

    expect(screen.getByTestId(ElementIds.JJ_IDENTITY).textContent).toContain("once jj");
    expect(screen.queryByTestId(ElementIds.JJ_IDENTITY_FORM)).toBeNull();
  });
});
