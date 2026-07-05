import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { PrimitiveAtom } from "jotai";
import { atom, createStore, Provider } from "jotai";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "../api";
import type { ErrorToastData } from "../common/state/atoms/toasts.ts";
import { ToastProvider, ToastType } from "../components/Toast.tsx";
import { AtomToast } from "./AtomToast.tsx";

afterEach(cleanup);

// A fresh atom per test so state never leaks between cases. Typed like the real
// error-toast atoms (required description/type/action) to prove those payloads
// remain assignable to AtomToast's wider optional-field contract.
const makeToastAtom = (): PrimitiveAtom<ErrorToastData | null> => atom<ErrorToastData | null>(null);

const renderToast = (toastAtom: PrimitiveAtom<ErrorToastData | null>): { store: ReturnType<typeof createStore> } => {
  const store = createStore();
  const ui: ReactElement = (
    <Provider store={store}>
      <ToastProvider>
        <AtomToast toastAtom={toastAtom} />
      </ToastProvider>
    </Provider>
  );
  render(ui);
  return { store };
};

describe("AtomToast", () => {
  it("stays closed while the atom is null", () => {
    renderToast(makeToastAtom());

    expect(screen.queryByTestId(ElementIds.TOAST)).toBeNull();
  });

  it("opens with the atom payload, including the action button", () => {
    const toastAtom = makeToastAtom();
    const handleRetry = vi.fn();
    const { store } = renderToast(toastAtom);

    act(() => {
      store.set(toastAtom, {
        title: "Delete failed",
        description: "The workspace could not be deleted.",
        type: ToastType.ERROR,
        action: { label: "Retry", handleClick: handleRetry },
      });
    });

    expect(screen.getByText("Delete failed")).toBeInTheDocument();
    expect(screen.getByText("The workspace could not be deleted.")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId(ElementIds.TOAST_ACTION_BUTTON));
    expect(handleRetry).toHaveBeenCalledTimes(1);
  });

  it("clears the atom when the toast is dismissed", () => {
    const toastAtom = makeToastAtom();
    const { store } = renderToast(toastAtom);

    act(() => {
      store.set(toastAtom, {
        title: "Something broke",
        description: null,
        type: ToastType.ERROR,
        action: null,
      });
    });
    expect(screen.getByTestId(ElementIds.TOAST)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId(ElementIds.TOAST_CLOSE_BUTTON));
    expect(store.get(toastAtom)).toBeNull();
  });
});
