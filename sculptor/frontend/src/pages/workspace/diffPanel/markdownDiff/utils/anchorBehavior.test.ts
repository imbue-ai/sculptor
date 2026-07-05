import type { MouseEvent as ReactMouseEvent } from "react";
import { describe, expect, it, vi } from "vitest";

import { handleInternalMarkdownAnchorClick, hasExternalProtocol } from "./anchorBehavior.ts";

describe("hasExternalProtocol", () => {
  it("recognises common URL schemes", () => {
    expect(hasExternalProtocol("https://example.com")).toBe(true);
    expect(hasExternalProtocol("http://example.com")).toBe(true);
    expect(hasExternalProtocol("HTTPS://example.com")).toBe(true);
    expect(hasExternalProtocol("mailto:user@example.com")).toBe(true);
    expect(hasExternalProtocol("ftp://example.com/x")).toBe(true);
  });

  it("treats fragments and relative paths as internal", () => {
    expect(hasExternalProtocol("#section")).toBe(false);
    expect(hasExternalProtocol("./neighbor.md")).toBe(false);
    expect(hasExternalProtocol("../sibling.md")).toBe(false);
    expect(hasExternalProtocol("/absolute/path")).toBe(false);
    expect(hasExternalProtocol("just-a-word")).toBe(false);
    expect(hasExternalProtocol("")).toBe(false);
  });
});

// Build a synthetic React MouseEvent that satisfies the bits of the API the
// click handler actually inspects. Keeping it manual avoids dragging in a
// full DOM testing harness for what is otherwise a tiny pure function.
const fakeEvent = (anchor: HTMLAnchorElement): ReactMouseEvent<HTMLAnchorElement> => {
  const preventDefault = vi.fn();
  return { preventDefault, currentTarget: anchor } as unknown as ReactMouseEvent<HTMLAnchorElement>;
};

describe("handleInternalMarkdownAnchorClick", () => {
  it("calls preventDefault for fragment-only links", () => {
    const a = document.createElement("a");
    a.setAttribute("href", "#section");
    const event = fakeEvent(a);
    handleInternalMarkdownAnchorClick(event);
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
  });

  it("calls preventDefault for relative-path links", () => {
    const a = document.createElement("a");
    a.setAttribute("href", "./neighbor.md");
    const event = fakeEvent(a);
    handleInternalMarkdownAnchorClick(event);
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
  });

  it("calls preventDefault even for an empty href", () => {
    const a = document.createElement("a");
    const event = fakeEvent(a);
    handleInternalMarkdownAnchorClick(event);
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
  });

  it("scrolls to a matching id inside the same markdown body", () => {
    const body = document.createElement("div");
    body.setAttribute("data-markdown-body", "");
    const target = document.createElement("h2");
    target.id = "install";
    const scrollIntoView = vi.fn();
    target.scrollIntoView = scrollIntoView;
    const a = document.createElement("a");
    a.setAttribute("href", "#install");
    body.append(a, target);
    document.body.append(body);

    try {
      handleInternalMarkdownAnchorClick(fakeEvent(a));
      expect(scrollIntoView).toHaveBeenCalledTimes(1);
    } finally {
      body.remove();
    }
  });

  it("does not scroll across markdown bodies", () => {
    // Two separate markdown bodies, each with their own #install. A click in
    // body A must not scroll an h2#install that lives in body B.
    const bodyA = document.createElement("div");
    bodyA.setAttribute("data-markdown-body", "");
    const bodyB = document.createElement("div");
    bodyB.setAttribute("data-markdown-body", "");
    const targetB = document.createElement("h2");
    targetB.id = "install";
    const scrollIntoView = vi.fn();
    targetB.scrollIntoView = scrollIntoView;
    const a = document.createElement("a");
    a.setAttribute("href", "#install");
    bodyA.append(a);
    bodyB.append(targetB);
    document.body.append(bodyA, bodyB);

    try {
      handleInternalMarkdownAnchorClick(fakeEvent(a));
      expect(scrollIntoView).not.toHaveBeenCalled();
    } finally {
      bodyA.remove();
      bodyB.remove();
    }
  });

  it("is a safe no-op on a fragment with no matching id (TOC link before SCU-767 lands)", () => {
    const body = document.createElement("div");
    body.setAttribute("data-markdown-body", "");
    const a = document.createElement("a");
    a.setAttribute("href", "#nope");
    body.append(a);
    document.body.append(body);

    try {
      // Should not throw and should still preventDefault.
      const event = fakeEvent(a);
      handleInternalMarkdownAnchorClick(event);
      expect(event.preventDefault).toHaveBeenCalledTimes(1);
    } finally {
      body.remove();
    }
  });
});
