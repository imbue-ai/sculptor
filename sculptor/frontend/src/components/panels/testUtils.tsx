import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { render } from "@testing-library/react";
import type { createStore } from "jotai";
import { Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { PanelRegistryProvider } from "~/components/panels/PanelRegistryProvider";
import type { PanelDefinition } from "~/components/panels/types.ts";

type Store = ReturnType<typeof createStore>;

type RenderWithProvidersResult = RenderResult & { store: Store };

type RenderWithProvidersOptions = {
  store: Store;
  panels?: ReadonlyArray<PanelDefinition>;
  initialEntries?: ReadonlyArray<string>;
};

export const renderWithProviders = (ui: ReactNode, options: RenderWithProvidersOptions): RenderWithProvidersResult => {
  const { store, panels, initialEntries } = options;
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>
        <MemoryRouter initialEntries={initialEntries ? [...initialEntries] : undefined}>
          {panels ? <PanelRegistryProvider panels={panels}>{children}</PanelRegistryProvider> : children}
        </MemoryRouter>
      </Theme>
    </Provider>
  );

  return Object.assign(render(ui, { wrapper: Wrapper }), { store });
};
