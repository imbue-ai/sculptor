import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { DependencyInfo, JjReadiness } from "~/api";
import { ElementIds } from "~/api";

import { JjAvailabilityCallout } from "./JjAvailabilityCallout.tsx";

afterEach(() => {
  cleanup();
});

const renderCallout = (readiness: JjReadiness, jj: DependencyInfo): ReactElement => (
  <Theme>
    <JjAvailabilityCallout readiness={readiness} jj={jj} minimumVersion="0.46.0" />
  </Theme>
);

const availabilityText = (): string => screen.getByTestId(ElementIds.JJ_AVAILABILITY).textContent ?? "";

describe("JjAvailabilityCallout", () => {
  it("names the version and the managed source when jj is available", () => {
    render(
      renderCallout(
        { blocker: null, identity: { name: "Ada", email: "ada@example.com" } },
        { installed: true, version: "0.46.0", source: "MANAGED", path: "/managed/jj" },
      ),
    );
    expect(availabilityText()).toContain("jj 0.46.0 is available");
    expect(availabilityText()).toContain("managed by Sculptor");
  });

  it("names the path of an external jj", () => {
    render(
      renderCallout(
        { blocker: null, identity: { name: "Ada", email: "ada@example.com" } },
        { installed: true, version: "0.47.1", source: "EXTERNAL", path: "/opt/homebrew/bin/jj" },
      ),
    );
    expect(availabilityText()).toContain("/opt/homebrew/bin/jj");
  });

  it("shows an unsupported version's detail and asks for a compatible jj", () => {
    render(
      renderCallout(
        { blocker: "UNSUPPORTED_VERSION", detail: "/usr/bin/jj reports jj 0.28.2" },
        { installed: true, version: "0.28.2", path: "/usr/bin/jj" },
      ),
    );
    expect(availabilityText()).toContain("/usr/bin/jj reports jj 0.28.2");
    expect(availabilityText()).toContain("Sculptor needs jj 0.46.0 or a newer compatible version");
  });

  it("does not ask a jj that is too new to be newer", () => {
    render(
      renderCallout(
        { blocker: "UNSUPPORTED_VERSION", detail: "/usr/bin/jj reports jj 1.0.0" },
        { installed: true, version: "1.0.0", path: "/usr/bin/jj" },
      ),
    );
    expect(availabilityText()).not.toContain("or later");
    expect(availabilityText()).not.toContain("a newer jj");
  });

  it("shows why jj does not run", () => {
    render(
      renderCallout(
        { blocker: "NOT_RUNNABLE", detail: "Config error: Configuration cannot be parsed as TOML document" },
        { installed: false, path: "/usr/bin/jj" },
      ),
    );
    expect(availabilityText()).toContain("Config error: Configuration cannot be parsed as TOML document");
  });

  it("points a missing identity at the identity form", () => {
    render(renderCallout({ blocker: "NO_IDENTITY" }, { installed: true, version: "0.46.0", path: "/usr/bin/jj" }));
    expect(availabilityText()).toContain("author identity");
  });

  it("points a missing jj at installing it or setting a path", () => {
    render(renderCallout({ blocker: "NOT_INSTALLED" }, { installed: false }));
    expect(availabilityText()).toContain("Install");
  });
});
