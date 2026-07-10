import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RegisteredAgentLabel } from "./RegisteredAgentLabel";

afterEach(() => {
  cleanup();
});

describe("RegisteredAgentLabel", () => {
  it("renders the display name alongside a distinct 'terminal' origin tag", () => {
    render(
      <Theme>
        <RegisteredAgentLabel displayName="My Agent" />
      </Theme>,
    );
    // The tag is its own element (so it can be styled muted); the name is not
    // swallowed into it.
    expect(screen.getByText("terminal")).toBeTruthy();
    expect(screen.getByText(/My Agent/)).toBeTruthy();
  });

  it("separates the name and tag with a literal space so the accessible name reads as two words", () => {
    const { container } = render(
      <Theme>
        <RegisteredAgentLabel displayName="My Agent" />
      </Theme>,
    );
    // A real space (not just the CSS gap) sits between the name and the tag, so
    // screen readers and Radix Select typeahead see "My Agent terminal" rather
    // than "My Agentterminal".
    expect(container.textContent).toBe("My Agent terminal");
  });
});
