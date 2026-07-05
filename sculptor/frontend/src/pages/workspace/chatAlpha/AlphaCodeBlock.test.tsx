import { Theme } from "@radix-ui/themes";
import { cleanup, render as rtlRender, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DualThemedToken } from "./shikiHighlighter.ts";

const ThemeWrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;
const render = (
  ui: ReactElement,
  options?: Omit<Parameters<typeof rtlRender>[1], "wrapper">,
): ReturnType<typeof rtlRender> => rtlRender(ui, { wrapper: ThemeWrapper, ...options });

vi.mock("./shikiHighlighter.ts", () => ({
  highlightCode: vi.fn(
    async (
      code: string,
      language: string,
      _themes: { light: string; dark: string },
    ): Promise<ReadonlyArray<ReadonlyArray<DualThemedToken>> | null> => {
      if (language === "not-a-real-language") return null;
      return [[{ content: code, lightColor: "#24292E", darkColor: "#E1E4E8" }]];
    },
  ),
}));

import { AlphaCodeBlock } from "./AlphaCodeBlock.tsx";

afterEach(cleanup);

describe("AlphaCodeBlock", () => {
  it("renders code content in a pre > code structure", () => {
    const { container } = render(<AlphaCodeBlock content="const x = 1;" />);
    const pre = container.querySelector("pre");
    expect(pre).toBeTruthy();
    const code = pre!.querySelector("code");
    expect(code).toBeTruthy();
    expect(code!.textContent).toBe("const x = 1;");
  });

  it("sets data-language attribute when language is provided", () => {
    const { container } = render(<AlphaCodeBlock content="print('hi')" language="python" />);
    const pre = container.querySelector("pre");
    expect(pre!.getAttribute("data-language")).toBe("python");
  });

  it("does not set data-language when language is omitted", () => {
    const { container } = render(<AlphaCodeBlock content="some code" />);
    const pre = container.querySelector("pre");
    expect(pre!.getAttribute("data-language")).toBeNull();
  });

  it("preserves whitespace in code content", () => {
    const code = "function foo() {\n  return 1;\n}";
    const { container } = render(<AlphaCodeBlock content={code} />);
    expect(container.querySelector("code")!.textContent).toBe(code);
  });

  it("applies syntax highlighting when a language is provided", async () => {
    const { container } = render(<AlphaCodeBlock content='print("hello")' language="python" />);

    // Highlighting is async — wait for token spans to appear inside code > span > span
    await waitFor(() => {
      const tokenSpans = container.querySelectorAll("code > span > span");
      expect(tokenSpans.length).toBeGreaterThan(0);
    });

    expect(container.querySelector("code")!.textContent).toContain("print");
  });

  it("renders plain text for unsupported languages", async () => {
    const { container } = render(<AlphaCodeBlock content="some code\n" language="not-a-real-language" />);

    // The highlighter rejects/returns null for this language, leaving plain text.
    await waitFor(() => {
      expect(container.querySelector("code")!.textContent).toContain("some code");
    });
  });

  it("renders plain text when no language is provided", () => {
    const code = "just some plain text";
    const { container } = render(<AlphaCodeBlock content={code} />);
    expect(container.querySelector("code")!.textContent).toBe(code);
    // Plain text still uses line-based <span> structure (matching highlighted
    // layout), but no token has an inline style (no syntax colors).
    const tokenSpans = container.querySelectorAll("code > span > span");
    for (const span of tokenSpans) {
      expect(span.getAttribute("style")).toBeNull();
    }
  });

  it("renders multi-line tokens with newline separators between lines", async () => {
    const { highlightCode } = await import("./shikiHighlighter.ts");
    vi.mocked(highlightCode).mockResolvedValueOnce([
      [{ content: "line1", lightColor: "#000", darkColor: "#fff" }],
      [{ content: "line2", lightColor: "#000", darkColor: "#fff" }],
      [{ content: "line3", lightColor: "#000", darkColor: "#fff" }],
    ]);

    const { container } = render(<AlphaCodeBlock content="line1\nline2\nline3\n" language="python" />);

    await waitFor(() => {
      const lineSpans = container.querySelectorAll("code > span");
      expect(lineSpans).toHaveLength(3);
    });

    expect(container.querySelector("code")!.textContent).toBe("line1\nline2\nline3");
  });

  it("renders individual token spans with correct text content", async () => {
    const { highlightCode } = await import("./shikiHighlighter.ts");
    vi.mocked(highlightCode).mockResolvedValueOnce([
      [
        { content: "const", lightColor: "#CF222E", darkColor: "#FF7B72" },
        { content: " x", lightColor: "#000", darkColor: "#fff" },
      ],
    ]);

    const { container } = render(<AlphaCodeBlock content="const x\n" language="python" />);

    await waitFor(() => {
      const tokenSpans = container.querySelectorAll("code > span > span");
      expect(tokenSpans).toHaveLength(2);
      expect(tokenSpans[0].textContent).toBe("const");
      expect(tokenSpans[1].textContent).toBe(" x");
    });
  });

  it("falls back to plain text when content changes to unsupported language", async () => {
    const { highlightCode } = await import("./shikiHighlighter.ts");

    // First render: supported language with tokens
    vi.mocked(highlightCode).mockResolvedValueOnce([[{ content: "print", lightColor: "#000", darkColor: "#fff" }]]);

    const { container, rerender } = render(<AlphaCodeBlock content='print("hi")\n' language="python" />);

    await waitFor(() => {
      expect(container.querySelectorAll("code > span > span").length).toBeGreaterThan(0);
    });

    // Rerender with unsupported language — should fall back to plain text
    rerender(<AlphaCodeBlock content="some code\n" language="not-a-real-language" />);

    await waitFor(() => {
      // Token spans should be gone, plain text should show
      expect(container.querySelector("code")!.textContent).toContain("some code");
    });
  });
});
