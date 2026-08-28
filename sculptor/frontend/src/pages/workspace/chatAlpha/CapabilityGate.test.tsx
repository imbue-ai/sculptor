import { Button, Theme } from "@radix-ui/themes";
import { cleanup, render, screen, within } from "@testing-library/react";
import { ListChecks } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { ElementIds } from "~/api";

import { CAPABILITY_UNSUPPORTED_COPY, useCapabilityGate } from "../../../common/hooks/useCapabilityGate";
import { CapabilityGate } from "./CapabilityGate";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

const ENABLED_TESTID = ElementIds.PLAN_MODE_TOGGLE;
const DISABLED_TESTID = ElementIds.CAPABILITY_DISABLED_PLAN_MODE;

afterEach(() => {
  cleanup();
});

describe("useCapabilityGate", () => {
  it("is enabled when the capability is true", () => {
    expect(useCapabilityGate(true, DISABLED_TESTID)).toEqual({ enabled: true });
  });

  it("is enabled when the capability has not loaded yet (load-race optimism)", () => {
    expect(useCapabilityGate(undefined, DISABLED_TESTID)).toEqual({ enabled: true });
  });

  it("is disabled with standardized copy and the ElementID when the capability is false", () => {
    expect(useCapabilityGate(false, DISABLED_TESTID)).toEqual({
      enabled: false,
      tooltip: CAPABILITY_UNSUPPORTED_COPY,
      elementId: DISABLED_TESTID,
    });
  });
});

describe("CapabilityGate", () => {
  const renderGate = (capabilityValue: boolean | undefined): void => {
    render(
      <Wrapper>
        <CapabilityGate
          capabilityValue={capabilityValue}
          elementId={DISABLED_TESTID}
          disabledIcon={<ListChecks size={16} />}
        >
          <Button data-testid={ENABLED_TESTID}>enabled affordance</Button>
        </CapabilityGate>
      </Wrapper>,
    );
  };

  it("renders the enabled affordance untouched when the capability holds", () => {
    renderGate(true);
    expect(screen.getByTestId(ENABLED_TESTID)).toBeInTheDocument();
    expect(screen.queryByTestId(DISABLED_TESTID)).not.toBeInTheDocument();
  });

  it("keeps the affordance enabled while the capability is still loading", () => {
    renderGate(undefined);
    expect(screen.getByTestId(ENABLED_TESTID)).toBeInTheDocument();
    expect(screen.queryByTestId(DISABLED_TESTID)).not.toBeInTheDocument();
  });

  it("replaces it with a disabled placeholder carrying the ElementID when the capability is false", () => {
    renderGate(false);
    expect(screen.queryByTestId(ENABLED_TESTID)).not.toBeInTheDocument();
    const placeholder = screen.getByTestId(DISABLED_TESTID);
    expect(placeholder).toBeInTheDocument();
    expect(within(placeholder).getByRole("button")).toBeDisabled();
  });
});
