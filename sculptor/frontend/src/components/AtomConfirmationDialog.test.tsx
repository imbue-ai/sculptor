import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { PrimitiveAtom } from "jotai";
import { atom, createStore, Provider } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "../api";
import type { ConfirmationDialogData } from "../common/state/atoms/confirmationDialog.ts";
import { AtomConfirmationDialog } from "./AtomConfirmationDialog.tsx";

afterEach(cleanup);

// A fresh atom per test so state never leaks between cases.
const makeDialogAtom = (): PrimitiveAtom<ConfirmationDialogData | null> => atom<ConfirmationDialogData | null>(null);

const renderDialog = (
  dialogAtom: PrimitiveAtom<ConfirmationDialogData | null>,
): { store: ReturnType<typeof createStore> } => {
  const store = createStore();
  render(
    <Provider store={store}>
      <Theme>
        <AtomConfirmationDialog dialogAtom={dialogAtom} />
      </Theme>
    </Provider>,
  );
  return { store };
};

const sampleData = (onConfirm: () => void): ConfirmationDialogData => ({
  title: "Reset to default layout?",
  description: "This discards your current arrangement.",
  confirmLabel: "Reset layout",
  tone: "neutral",
  onConfirm,
});

describe("AtomConfirmationDialog", () => {
  it("stays closed while the atom is null", () => {
    renderDialog(makeDialogAtom());

    expect(screen.queryByTestId(ElementIds.CONFIRMATION_DIALOG)).toBeNull();
  });

  it("opens with the atom payload", () => {
    const dialogAtom = makeDialogAtom();
    const { store } = renderDialog(dialogAtom);

    act(() => {
      store.set(dialogAtom, sampleData(vi.fn()));
    });

    expect(screen.getByText("Reset to default layout?")).toBeInTheDocument();
    expect(screen.getByText("This discards your current arrangement.")).toBeInTheDocument();
  });

  it("runs onConfirm and clears the atom when confirmed", () => {
    const dialogAtom = makeDialogAtom();
    const handleConfirm = vi.fn();
    const { store } = renderDialog(dialogAtom);

    act(() => {
      store.set(dialogAtom, sampleData(handleConfirm));
    });

    fireEvent.click(screen.getByTestId(ElementIds.CONFIRMATION_DIALOG_CONFIRM));
    expect(handleConfirm).toHaveBeenCalledTimes(1);
    expect(store.get(dialogAtom)).toBeNull();
  });

  it("clears the atom without running onConfirm when cancelled", () => {
    const dialogAtom = makeDialogAtom();
    const handleConfirm = vi.fn();
    const { store } = renderDialog(dialogAtom);

    act(() => {
      store.set(dialogAtom, sampleData(handleConfirm));
    });

    fireEvent.click(screen.getByTestId(ElementIds.CONFIRMATION_DIALOG_CANCEL));
    expect(handleConfirm).not.toHaveBeenCalled();
    expect(store.get(dialogAtom)).toBeNull();
  });
});
