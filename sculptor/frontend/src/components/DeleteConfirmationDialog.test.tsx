import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { DeleteConfirmationDialog } from "./DeleteConfirmationDialog";
import { POPOVER_FRIENDLY_MODAL_ATTRIBUTE, popoverFriendlyModalGuard } from "./popoverFriendlyModal";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

afterEach(() => {
  cleanup();
});

describe("DeleteConfirmationDialog — popover-friendly marker", () => {
  it("tags the dialog content with the popover-friendly marker while open", () => {
    render(
      <Wrapper>
        <DeleteConfirmationDialog
          isOpen
          onOpenChange={(): void => {}}
          entityType="workspace"
          entityName="ws-1"
          onConfirm={(): void => {}}
        />
      </Wrapper>,
    );

    const content = screen.getByTestId(ElementIds.DELETE_CONFIRMATION_DIALOG);
    expect(content.getAttribute(POPOVER_FRIENDLY_MODAL_ATTRIBUTE)).toBe("true");
  });

  it("renders nothing markable when closed", () => {
    render(
      <Wrapper>
        <DeleteConfirmationDialog
          isOpen={false}
          onOpenChange={(): void => {}}
          entityType="workspace"
          entityName="ws-1"
          onConfirm={(): void => {}}
        />
      </Wrapper>,
    );

    expect(screen.queryByTestId(ElementIds.DELETE_CONFIRMATION_DIALOG)).toBeNull();
    expect(document.querySelector(`[${POPOVER_FRIENDLY_MODAL_ATTRIBUTE}="true"]`)).toBeNull();
  });
});

describe("popoverFriendlyModalGuard.onInteractOutside", () => {
  // Build a synthetic Radix-style outside event around a real DOM target.
  // The guard only reads `event.target` and may call `event.preventDefault()`.
  const makeEvent = (
    target: EventTarget | null,
  ): { target: EventTarget | null; preventDefault: ReturnType<typeof vi.fn> } => ({
    target,
    preventDefault: vi.fn(),
  });

  it("calls preventDefault when the event target is inside a popover-friendly modal", () => {
    const modal = document.createElement("div");
    modal.setAttribute(POPOVER_FRIENDLY_MODAL_ATTRIBUTE, "true");
    const inner = document.createElement("button");
    modal.appendChild(inner);
    document.body.appendChild(modal);

    const event = makeEvent(inner);
    // The Radix event type is a CustomEvent; the guard only touches the
    // minimal shape covered by `makeEvent`.
    popoverFriendlyModalGuard.onInteractOutside?.(
      event as unknown as Parameters<NonNullable<typeof popoverFriendlyModalGuard.onInteractOutside>>[0],
    );

    expect(event.preventDefault).toHaveBeenCalledTimes(1);
    document.body.removeChild(modal);
  });

  it("calls preventDefault when the target IS the marked element itself", () => {
    const modal = document.createElement("div");
    modal.setAttribute(POPOVER_FRIENDLY_MODAL_ATTRIBUTE, "true");
    document.body.appendChild(modal);

    const event = makeEvent(modal);
    popoverFriendlyModalGuard.onInteractOutside?.(
      event as unknown as Parameters<NonNullable<typeof popoverFriendlyModalGuard.onInteractOutside>>[0],
    );

    expect(event.preventDefault).toHaveBeenCalledTimes(1);
    document.body.removeChild(modal);
  });

  it("does NOT call preventDefault when the target is outside any popover-friendly modal", () => {
    const other = document.createElement("div");
    document.body.appendChild(other);

    const event = makeEvent(other);
    popoverFriendlyModalGuard.onInteractOutside?.(
      event as unknown as Parameters<NonNullable<typeof popoverFriendlyModalGuard.onInteractOutside>>[0],
    );

    expect(event.preventDefault).not.toHaveBeenCalled();
    document.body.removeChild(other);
  });

  it("does NOT call preventDefault when the target has the attribute but with a falsey value", () => {
    // Explicit `false` value should not match the `[attr="true"]` selector.
    const sibling = document.createElement("div");
    sibling.setAttribute(POPOVER_FRIENDLY_MODAL_ATTRIBUTE, "false");
    document.body.appendChild(sibling);

    const event = makeEvent(sibling);
    popoverFriendlyModalGuard.onInteractOutside?.(
      event as unknown as Parameters<NonNullable<typeof popoverFriendlyModalGuard.onInteractOutside>>[0],
    );

    expect(event.preventDefault).not.toHaveBeenCalled();
    document.body.removeChild(sibling);
  });

  it("does NOT call preventDefault when the target is null (e.g., events without a target)", () => {
    const event = makeEvent(null);
    popoverFriendlyModalGuard.onInteractOutside?.(
      event as unknown as Parameters<NonNullable<typeof popoverFriendlyModalGuard.onInteractOutside>>[0],
    );

    expect(event.preventDefault).not.toHaveBeenCalled();
  });
});
