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
        { blocker: "UNSUPPORTED_VERSION", path: "/usr/bin/jj", version: "0.28.2" },
        { installed: true, version: "0.28.2", path: "/usr/bin/jj" },
      ),
    );
    expect(availabilityText()).toContain("/usr/bin/jj reports jj 0.28.2");
    expect(availabilityText()).toContain("Sculptor needs jj 0.46.0 or a newer compatible version");
  });

  it("does not ask a jj that is too new to be newer", () => {
    render(
      renderCallout(
        { blocker: "UNSUPPORTED_VERSION", path: "/usr/bin/jj", version: "1.0.0" },
        { installed: true, version: "1.0.0", path: "/usr/bin/jj" },
      ),
    );
    expect(availabilityText()).not.toContain("or later");
    expect(availabilityText()).not.toContain("a newer jj");
  });

  it("names the binary whose version output it could not read", () => {
    render(
      renderCallout(
        { blocker: "UNSUPPORTED_VERSION", path: "/usr/bin/jj", version: null },
        { installed: true, version: null, path: "/usr/bin/jj" },
      ),
    );
    expect(availabilityText()).toContain("/usr/bin/jj reports no recognizable jj version");
  });

  it("names the git jj runs and the oldest git jj accepts when that git is too old", () => {
    render(
      renderCallout(
        { blocker: "UNSUPPORTED_GIT", path: "/usr/bin/git", version: "2.39.5", minimumVersion: "2.42.0" },
        { installed: true, version: "0.46.0", source: "MANAGED", path: "/managed/jj" },
      ),
    );
    expect(availabilityText()).toContain("/usr/bin/git reports git 2.39.5");
    expect(availabilityText()).toContain("jj needs git 2.42.0 or newer");
    expect(availabilityText()).toContain("git.executable-path");
  });

  it("says when jj finds no git to run", () => {
    render(
      renderCallout(
        { blocker: "UNSUPPORTED_GIT", path: null, version: null, minimumVersion: "2.42.0" },
        { installed: true, version: "0.46.0", source: "MANAGED", path: "/managed/jj" },
      ),
    );
    expect(availabilityText()).toContain("jj finds no git");
    expect(availabilityText()).toContain("jj needs git 2.42.0 or newer");
  });

  it("names the jj the login shell runs instead of Sculptor's and says how to stop it", () => {
    render(
      renderCallout(
        { blocker: "SHADOWED", path: "/home/dev/.cargo/bin/jj", version: "0.28.2" },
        { installed: true, version: "0.46.0", source: "MANAGED", path: "/managed/jj" },
      ),
    );
    expect(availabilityText()).toContain("/home/dev/.cargo/bin/jj reports jj 0.28.2");
    expect(availabilityText()).toContain("Sculptor needs jj 0.46.0 or a newer compatible version");
    expect(availabilityText()).toContain("shared with the jj you run yourself");
    expect(availabilityText()).toContain("first on PATH");
  });

  it("shows why jj does not run", () => {
    render(
      renderCallout(
        { blocker: "NOT_RUNNABLE", error: "Config error: Configuration cannot be parsed as TOML document" },
        { installed: false, path: "/usr/bin/jj" },
      ),
    );
    expect(availabilityText()).toContain("Config error: Configuration cannot be parsed as TOML document");
  });

  it("points a missing identity at the identity form", () => {
    render(
      renderCallout(
        { blocker: "NO_IDENTITY", suggestedIdentity: { name: "", email: "" } },
        { installed: true, version: "0.46.0", path: "/usr/bin/jj" },
      ),
    );
    expect(availabilityText()).toContain("author identity");
  });

  it("points a missing jj at installing it or setting a path", () => {
    render(renderCallout({ blocker: "NOT_INSTALLED" }, { installed: false }));
    expect(availabilityText()).toContain("Install");
  });
});
