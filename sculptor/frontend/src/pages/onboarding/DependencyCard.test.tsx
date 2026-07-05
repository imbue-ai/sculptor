import { Theme } from "@radix-ui/themes";
import { cleanup, render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { DependencyCard } from "./DependencyCard";
import type { DependencyStatus } from "./types/dependency.ts";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

afterEach(() => {
  cleanup();
});

const renderCard = (status: DependencyStatus): HTMLElement => {
  const { container } = render(
    <Wrapper>
      <DependencyCard name="Claude" cliName="claude" status={status} installUrl="https://example.com" />
    </Wrapper>,
  );
  const card = container.querySelector<HTMLElement>('[data-dependency="claude"]');
  if (card === null) {
    throw new Error("dependency card not found");
  }
  return card;
};

// SCU-1215: the card gates `handleToggle` on `canExpand`. That gate must be
// reflected in the DOM via `aria-disabled` so the framework's actionability
// contract blocks a click until the card is ready — otherwise a click landing
// while the dependency probe is in flight is silently dropped by the handler's
// early-return. These tests pin the attribute to the gate deterministically,
// independent of probe timing.
describe("DependencyCard — readiness reflected via aria-disabled", () => {
  it("is aria-disabled while the dependency probe is loading", () => {
    expect(renderCard({ state: "loading" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("is aria-disabled while installing", () => {
    expect(renderCard({ state: "installing" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("is aria-disabled while authenticating", () => {
    const status: DependencyStatus = { state: "authenticating", path: "/usr/local/bin/claude", version: "1.0.0" };
    expect(renderCard(status).getAttribute("aria-disabled")).toBe("true");
  });

  it("is not aria-disabled once the dependency is installed", () => {
    const status: DependencyStatus = { state: "installed", path: "/usr/local/bin/claude", version: "1.0.0" };
    expect(renderCard(status).getAttribute("aria-disabled")).toBe("false");
  });

  it("is not aria-disabled when the dependency is not installed", () => {
    expect(renderCard({ state: "not-installed" }).getAttribute("aria-disabled")).toBe("false");
  });
});
