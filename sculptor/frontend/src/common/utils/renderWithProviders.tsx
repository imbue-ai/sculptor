import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { render } from "@testing-library/react";
import type { createStore } from "jotai";
import { Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

type Store = ReturnType<typeof createStore>;

type RenderWithProvidersResult = RenderResult & { store: Store };

type RenderWithProvidersOptions = {
  store: Store;
  initialEntries?: ReadonlyArray<string>;
};

// Shared test helper: render a component inside the Jotai store, Radix Theme, and a
// MemoryRouter. The section/panel shell reads the registry from a module-level (global)
// atom, so the wrapper needs no extra provider seeding.
export const renderWithProviders = (ui: ReactNode, options: RenderWithProvidersOptions): RenderWithProvidersResult => {
  const { store, initialEntries } = options;
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>
        <MemoryRouter initialEntries={initialEntries ? [...initialEntries] : undefined}>{children}</MemoryRouter>
      </Theme>
    </Provider>
  );

  return Object.assign(render(ui, { wrapper: Wrapper }), { store });
};
