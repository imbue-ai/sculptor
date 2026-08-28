import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MarkdownAnchor } from "./MarkdownAnchor.tsx";

afterEach(cleanup);

// `MarkdownAnchor` is the single rendering point for every anchor in
// rendered file-markdown. These tests pin three things:
//   1. The right routing attributes are set for external vs fragment vs
//      relative hrefs, and each kind carries a `data-link-kind` attribute
//      that CSS can hook into.
//   2. The two unsupported kinds (fragment, relative) carry a default
//      `title` tooltip explaining that the click isn't wired up yet — a
//      caller-provided `title` (from markdown's `(href "title")` syntax)
//      still wins.
//   3. *Only* the documented props leak into the DOM. Both react-markdown
//      and hast-util-to-jsx-runtime hand component overrides a renderer-
//      internal `node` prop; if a caller accidentally spreads it onto the
//      <a>, React serialises it as `node="[object Object]"` — that's the
//      production bug guarded by the regression test below.

describe("MarkdownAnchor — external", () => {
  it("renders with target=_blank, rel=noopener noreferrer, and data-link-kind=external", () => {
    const { container } = render(<MarkdownAnchor href="https://example.com">click</MarkdownAnchor>);
    const a = container.querySelector("a");
    expect(a).not.toBeNull();
    expect(a!.getAttribute("href")).toBe("https://example.com");
    expect(a!.getAttribute("target")).toBe("_blank");
    expect(a!.getAttribute("rel")).toBe("noopener noreferrer");
    expect(a!.getAttribute("data-link-kind")).toBe("external");
    // Carries an ExternalLink lucide icon as a sibling of the link text.
    expect(a!.querySelector("svg")).not.toBeNull();
  });

  it("does not carry a default title (external links are supported)", () => {
    const { container } = render(<MarkdownAnchor href="https://example.com">click</MarkdownAnchor>);
    const a = container.querySelector("a");
    expect(a!.hasAttribute("title")).toBe(false);
  });

  it("preserves a caller-provided title verbatim", () => {
    const { container } = render(
      <MarkdownAnchor href="https://example.com" title="example tooltip">
        click
      </MarkdownAnchor>,
    );
    const a = container.querySelector("a");
    expect(a!.getAttribute("title")).toBe("example tooltip");
  });
});

describe("MarkdownAnchor — fragment", () => {
  it("renders without target/rel, with data-link-kind=fragment, a dashed-underline class, and a default 'not supported' title", () => {
    const { container } = render(<MarkdownAnchor href="#section">jump</MarkdownAnchor>);
    const a = container.querySelector("a");
    expect(a).not.toBeNull();
    expect(a!.getAttribute("href")).toBe("#section");
    expect(a!.hasAttribute("target")).toBe(false);
    expect(a!.hasAttribute("rel")).toBe(false);
    expect(a!.getAttribute("data-link-kind")).toBe("fragment");
    expect(a!.getAttribute("title")).toBe("In-page anchor links aren't supported yet");
    // Dashed-underline styling is applied via a className from the
    // colocated CSS module — the literal class name is hashed, so we
    // just confirm something was applied.
    expect(a!.className).not.toBe("");
    // No icon — the dashed underline IS the affordance.
    expect(a!.querySelector("svg")).toBeNull();
  });

  it("lets a caller-provided title win over the default", () => {
    const { container } = render(
      <MarkdownAnchor href="#section" title="markdown-provided tooltip">
        jump
      </MarkdownAnchor>,
    );
    const a = container.querySelector("a");
    expect(a!.getAttribute("title")).toBe("markdown-provided tooltip");
  });
});

describe("MarkdownAnchor — relative", () => {
  it("renders without target/rel, with data-link-kind=relative, a Link2Off icon, and a default 'not supported' title", () => {
    const { container } = render(<MarkdownAnchor href="./other.md">other</MarkdownAnchor>);
    const a = container.querySelector("a");
    expect(a).not.toBeNull();
    expect(a!.getAttribute("href")).toBe("./other.md");
    expect(a!.hasAttribute("target")).toBe(false);
    expect(a!.hasAttribute("rel")).toBe(false);
    expect(a!.getAttribute("data-link-kind")).toBe("relative");
    expect(a!.getAttribute("title")).toBe("Linked-file navigation isn't supported yet");
    // Carries a Link2Off (broken chain) lucide icon as the
    // "linked-file navigation isn't wired" affordance.
    expect(a!.querySelector("svg")).not.toBeNull();
  });

  it("lets a caller-provided title win over the default", () => {
    const { container } = render(
      <MarkdownAnchor href="./other.md" title="markdown-provided tooltip">
        other
      </MarkdownAnchor>,
    );
    const a = container.querySelector("a");
    expect(a!.getAttribute("title")).toBe("markdown-provided tooltip");
  });

  it("falls into the relative branch when no safe URL remains (e.g. javascript: stripped upstream)", () => {
    const { container } = render(<MarkdownAnchor href="">click</MarkdownAnchor>);
    const a = container.querySelector("a");
    expect(a).not.toBeNull();
    expect(a!.hasAttribute("href")).toBe(false);
    expect(a!.getAttribute("data-link-kind")).toBe("relative");
  });
});

describe("MarkdownAnchor — safety", () => {
  // The component itself runs `safeUrlTransform` on every incoming href so
  // it stays safe when a caller bypasses react-markdown's `urlTransform`
  // prop — notably the future `MarkdownDiff` consumer that goes through
  // `hast-util-to-jsx-runtime`. These cases pass dangerous hrefs DIRECTLY
  // (no upstream filter) and assert the dangerous URL never reaches the
  // DOM and the link doesn't get `target="_blank"` either.
  it.each([
    ["javascript:alert(1)"],
    ["JavaScript:alert(1)"],
    ["data:text/html,<script>alert(1)</script>"],
    ["vbscript:msgbox(1)"],
    ["file:///etc/passwd"],
  ])("strips %s without relying on an upstream urlTransform", (hostile: string) => {
    const { container } = render(<MarkdownAnchor href={hostile}>click</MarkdownAnchor>);
    const a = container.querySelector("a");
    expect(a).not.toBeNull();
    expect(a!.hasAttribute("href")).toBe(false);
    expect(a!.hasAttribute("target")).toBe(false);
    expect(a!.hasAttribute("rel")).toBe(false);
    // Falls into the relative branch — the stripped URL is empty, which
    // matches neither the external-protocol nor the fragment predicate.
    expect(a!.getAttribute("data-link-kind")).toBe("relative");
  });

  it('does not leak renderer-internal props onto the <a> (regression: react-markdown\'s `node` was being spread as `node="[object Object]"`)', () => {
    // We accept and pass through ONLY `href` / `title` / `children` — any
    // other prop callers hand us (intentionally or by accident) must not
    // reach the DOM. `node` is the production offender; assert there as
    // well as on a generic unknown attribute.
    const { container } = render(
      // @ts-expect-error — intentionally passing an unexpected prop
      <MarkdownAnchor href="https://example.com" node={{ type: "element" }} unknownThing="leak-me">
        click
      </MarkdownAnchor>,
    );
    const a = container.querySelector("a");
    expect(a).not.toBeNull();
    expect(a!.hasAttribute("node")).toBe(false);
    expect(a!.hasAttribute("unknownthing")).toBe(false);
    // Sanity: the documented attributes still made it.
    expect(a!.getAttribute("href")).toBe("https://example.com");
    expect(a!.getAttribute("target")).toBe("_blank");
  });
});
