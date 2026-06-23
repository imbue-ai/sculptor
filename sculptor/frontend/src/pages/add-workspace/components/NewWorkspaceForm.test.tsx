import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { createRef, type ReactElement, type ReactNode, type RefObject } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { NewWorkspaceForm } from "./NewWorkspaceForm";

const withProviders = (children: ReactNode): ReactElement => (
  <Provider store={createStore()}>
    <Theme>{children}</Theme>
  </Provider>
);

type RenderOpts = {
  onSubmit: () => void;
  nameInputRef: RefObject<HTMLInputElement | null>;
};

const renderForm = ({ onSubmit, nameInputRef }: RenderOpts): void => {
  render(
    withProviders(
      <NewWorkspaceForm
        workspaceName=""
        onWorkspaceNameChange={vi.fn()}
        nameInputRef={nameInputRef}
        repoInfo={null}
        isPending={false}
        onSubmit={onSubmit}
        autoFocus={false}
      >
        <div />
      </NewWorkspaceForm>,
    ),
  );
};

afterEach(() => {
  cleanup();
});

describe("NewWorkspaceForm", () => {
  // Regression: Cmd/Ctrl+Enter in the name input used to call onSubmit twice —
  // once from the input's own onKeyDown and once from the global document
  // keydown listener. The global listener now skips events whose target is the
  // name input (e.target === nameInputRef.current), so it fires exactly once.
  it("submits exactly once on Cmd/Ctrl+Enter from the name input", () => {
    const onSubmit = vi.fn();
    const nameInputRef = createRef<HTMLInputElement>();
    renderForm({ onSubmit, nameInputRef });

    const nameInput = screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT);
    nameInput.focus();

    // Set both modifiers so isModifierPressed() is true on either platform
    // (Mac reads metaKey, non-Mac reads ctrlKey).
    fireEvent.keyDown(nameInput, {
      key: "Enter",
      metaKey: true,
      ctrlKey: true,
    });

    // Old buggy behavior would call this twice (input handler + global listener).
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  // The global "submit from anywhere" listener should still fire for modified
  // Enter events that do NOT originate in the name input — this guards that the
  // fix narrowed the listener by target rather than disabling it.
  it("still submits once on Cmd/Ctrl+Enter dispatched outside the name input", () => {
    const onSubmit = vi.fn();
    const nameInputRef = createRef<HTMLInputElement>();
    renderForm({ onSubmit, nameInputRef });

    // Dispatch at the document level with a target that is not the name input.
    fireEvent.keyDown(document.body, {
      key: "Enter",
      metaKey: true,
      ctrlKey: true,
    });

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});
