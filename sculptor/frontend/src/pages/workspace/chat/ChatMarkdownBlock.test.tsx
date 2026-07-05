import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render as rtlRender, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { ChatAgentProvider } from "./ChatAgentContext.tsx";
import { ChatMarkdownBlock } from "./ChatMarkdownBlock.tsx";

const ThemeWrapper = ({ children }: { children: ReactNode }): ReactElement => (
  <ChatAgentProvider workspaceId="test-ws" agentId="agent-1">
    <Theme>{children}</Theme>
  </ChatAgentProvider>
);
const render = (
  ui: ReactElement,
  options?: Omit<Parameters<typeof rtlRender>[1], "wrapper">,
): ReturnType<typeof rtlRender> => rtlRender(ui, { wrapper: ThemeWrapper, ...options });

// Mock workspace hooks and Jotai atoms that ChatMarkdownBlock depends on

const mockOpenFileViewTab = vi.fn();

vi.mock("~/pages/workspace/hooks/useWorkspaceCodePath.ts", () => ({
  useWorkspaceCodePath: (): string => "/mock/workspace/code",
}));

vi.mock("jotai", async () => {
  const actual: Record<string, unknown> = await vi.importActual("jotai");
  return {
    ...actual,
    useSetAtom: (): typeof mockOpenFileViewTab => mockOpenFileViewTab,
  };
});

afterEach(() => {
  cleanup();
  mockOpenFileViewTab.mockClear();
});

describe("ChatMarkdownBlock", () => {
  it("renders plain text", () => {
    render(<ChatMarkdownBlock content="Hello world" />);
    expect(screen.getByText("Hello world")).toBeTruthy();
  });

  it("renders bold text", () => {
    const { container } = render(<ChatMarkdownBlock content="This is **bold** text" />);
    const strong = container.querySelector("strong");
    expect(strong).toBeTruthy();
    expect(strong!.textContent).toBe("bold");
  });

  it("renders italic text", () => {
    const { container } = render(<ChatMarkdownBlock content="This is *italic* text" />);
    const em = container.querySelector("em");
    expect(em).toBeTruthy();
    expect(em!.textContent).toBe("italic");
  });

  it("renders links with target=_blank", () => {
    render(<ChatMarkdownBlock content="Visit [Example](https://example.com)" />);
    const link = screen.getByText("Example");
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("renders h1 as native h1", () => {
    const { container } = render(<ChatMarkdownBlock content="# Heading One" />);
    expect(container.querySelector("h1")).toBeTruthy();
    expect(container.querySelector("h1")!.textContent).toBe("Heading One");
  });

  it("renders h2 as native h2", () => {
    const { container } = render(<ChatMarkdownBlock content="## Heading Two" />);
    expect(container.querySelector("h2")).toBeTruthy();
    expect(container.querySelector("h2")!.textContent).toBe("Heading Two");
  });

  it("renders h3 as native h3", () => {
    const { container } = render(<ChatMarkdownBlock content="### Heading Three" />);
    expect(container.querySelector("h3")).toBeTruthy();
    expect(container.querySelector("h3")!.textContent).toBe("Heading Three");
  });

  it("renders unordered lists", () => {
    const md = ["- Item one", "- Item two", "- Item three"].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toBe("Item one");
  });

  it("renders ordered lists", () => {
    const md = ["1. First", "2. Second", "3. Third"].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const ol = container.querySelector("ol");
    expect(ol).toBeTruthy();
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(3);
  });

  it("preserves the original marker on each item of a non-sequential ordered list", () => {
    // Regression for SCU-1311: remark-gfm follows CommonMark and renumbers an
    // ordered list sequentially from the first item's marker. The plugin in
    // ChatMarkdownBlock reads each item's original marker back out of the
    // source and emits ``<li value="N">`` so the browser displays the typed
    // number.
    const md = ["3. A", "", "17. B", "", "20. C"].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const items = Array.from(container.querySelectorAll("ol > li"));
    expect(items).toHaveLength(3);
    expect(items.map((li) => li.getAttribute("value"))).toEqual(["3", "17", "20"]);
  });

  it("still emits per-item values for a normal sequential ordered list (harmless)", () => {
    const md = ["1. First", "2. Second", "3. Third"].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const items = Array.from(container.querySelectorAll("ol > li"));
    expect(items.map((li) => li.getAttribute("value"))).toEqual(["1", "2", "3"]);
  });

  it("preserves markers when the list uses '1)' style markers", () => {
    const md = ["5) Alpha", "9) Bravo"].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const items = Array.from(container.querySelectorAll("ol > li"));
    expect(items).toHaveLength(2);
    expect(items.map((li) => li.getAttribute("value"))).toEqual(["5", "9"]);
  });

  it("leaves unordered lists untouched", () => {
    const md = ["- one", "- two"].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const items = Array.from(container.querySelectorAll("ul > li"));
    expect(items).toHaveLength(2);
    for (const li of items) {
      expect(li.getAttribute("value")).toBeNull();
    }
  });

  it("renders tables", () => {
    const markdown = "| Name | Value |\n|------|-------|\n| foo | 42 |\n| bar | 99 |";
    const { container } = render(<ChatMarkdownBlock content={markdown} />);
    expect(container.querySelector("table")).toBeTruthy();
    expect(container.querySelectorAll("th")).toHaveLength(2);
    expect(container.querySelectorAll("td")).toHaveLength(4);
  });

  it("renders code blocks with pre element", () => {
    const markdown = "```\nconst x = 1;\n```";
    const { container } = render(<ChatMarkdownBlock content={markdown} />);
    const pre = container.querySelector("pre");
    expect(pre).toBeTruthy();
    expect(pre!.textContent).toContain("const x = 1;");
  });

  it("renders inline code", () => {
    const { container } = render(<ChatMarkdownBlock content="Use `console.log` for debugging" />);
    const code = container.querySelector("code");
    expect(code).toBeTruthy();
    expect(code!.textContent).toBe("console.log");
  });

  it("suppresses images", () => {
    const { container } = render(<ChatMarkdownBlock content="![alt text](https://example.com/image.png)" />);
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders blockquotes", () => {
    const { container } = render(<ChatMarkdownBlock content="> This is a quote" />);
    expect(container.querySelector("blockquote")).toBeTruthy();
  });

  it("renders horizontal rules", () => {
    const md = ["Above", "", "---", "", "Below"].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} />);
    expect(container.querySelector("hr")).toBeTruthy();
  });

  it("handles empty content", () => {
    const { container } = render(<ChatMarkdownBlock content="" />);
    expect(container.firstChild).toBeTruthy();
  });

  // GFM extensions

  it("renders GFM task lists with checkboxes", () => {
    const md = ["- [x] Done", "- [ ] Todo"].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const checkboxes = container.querySelectorAll('input[type="checkbox"]');
    expect(checkboxes).toHaveLength(2);
    expect((checkboxes[0] as HTMLInputElement).checked).toBe(true);
    expect((checkboxes[1] as HTMLInputElement).checked).toBe(false);
  });

  it("renders strikethrough text", () => {
    const { container } = render(<ChatMarkdownBlock content="This is ~~deleted~~ text" />);
    const del = container.querySelector("del");
    expect(del).toBeTruthy();
    expect(del!.textContent).toBe("deleted");
  });

  // Nested / combined formatting

  it("renders nested blockquotes", () => {
    const md = ["> outer", "> ", "> > inner"].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const blockquotes = container.querySelectorAll("blockquote");
    expect(blockquotes.length).toBeGreaterThanOrEqual(2);
    // The inner blockquote should be nested inside the outer one
    const outerBq = container.querySelector("blockquote");
    expect(outerBq!.querySelector("blockquote")).toBeTruthy();
  });

  it("renders combined bold and italic", () => {
    const { container } = render(<ChatMarkdownBlock content="***bold and italic***" />);
    const strong = container.querySelector("strong");
    const em = container.querySelector("em");
    expect(strong).toBeTruthy();
    expect(em).toBeTruthy();
  });

  it("renders multiple paragraphs as separate p elements", () => {
    const md = ["Paragraph one.", "", "Paragraph two."].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const paragraphs = container.querySelectorAll("p");
    expect(paragraphs).toHaveLength(2);
    expect(paragraphs[0].textContent).toBe("Paragraph one.");
    expect(paragraphs[1].textContent).toBe("Paragraph two.");
  });

  // Code block routing

  it("routes fenced code blocks to ChatCodeBlock (pre > code structure)", () => {
    const md = "```python\nprint('hi')\n```";
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const pre = container.querySelector("pre");
    expect(pre).toBeTruthy();
    const code = pre!.querySelector("code");
    expect(code).toBeTruthy();
    expect(code!.textContent).toContain("print");
  });

  it("renders inline code with inlineCode styling, not as a code block", () => {
    const { container } = render(<ChatMarkdownBlock content="Use `foo` here" />);
    // Should NOT produce a <pre> (that would mean ChatCodeBlock was used)
    expect(container.querySelector("pre")).toBeNull();
    const code = container.querySelector("code");
    expect(code).toBeTruthy();
    expect(code!.textContent).toBe("foo");
  });

  // Table routing

  it("renders table data from markdown correctly", () => {
    const md = "| A | B |\n|---|---|\n| 1 | 2 |";
    const { container } = render(<ChatMarkdownBlock content={md} />);
    expect(container.querySelector("table")).toBeTruthy();
    expect(container.querySelectorAll("th")).toHaveLength(2);
    expect(container.querySelector("th")!.textContent).toBe("A");
    expect(container.querySelectorAll("td")).toHaveLength(2);
  });

  // Link security

  it("renders multiple links all with noopener noreferrer", () => {
    const md = "[A](https://a.com) and [B](https://b.com)";
    const { container } = render(<ChatMarkdownBlock content={md} />);
    const links = container.querySelectorAll("a");
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    }
  });

  // Image suppression edge cases

  it("suppresses images even when mixed with text", () => {
    const md = "Before ![img](https://example.com/img.png) after";
    const { container } = render(<ChatMarkdownBlock content={md} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("Before");
    expect(container.textContent).toContain("after");
  });

  // Search highlighting

  it("highlights search matches in plain text without error", () => {
    const { container } = render(
      <ChatMarkdownBlock content="hello world" searchQuery="hello" activeOccurrenceIndex={0} />,
    );
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("hello");
    expect(marks[0].className).toBe("chatSearchActive");
  });

  it("highlights search matches inside bold markdown without error", () => {
    const { container } = render(
      <ChatMarkdownBlock content="This is **bold hello** text" searchQuery="hello" activeOccurrenceIndex={0} />,
    );
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("hello");
    // The <mark> should be inside the <strong>
    expect(container.querySelector("strong mark")).toBeTruthy();
  });

  it("highlights search matches across multiple paragraphs", () => {
    const md = ["First hello paragraph.", "", "Second hello paragraph."].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} searchQuery="hello" activeOccurrenceIndex={1} />);
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(2);
  });

  it("applies active class to the match at activeOccurrenceIndex", () => {
    const md = ["First hello here.", "", "Second hello there."].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} searchQuery="hello" activeOccurrenceIndex={1} />);
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(2);
    expect(marks[0].className).toBe("chatSearchMatch");
    expect(marks[1].className).toBe("chatSearchActive");
  });

  it("highlights search matches inside fenced code blocks", () => {
    const md = "```\nhello world\n```";
    const { container } = render(<ChatMarkdownBlock content={md} searchQuery="hello" activeOccurrenceIndex={0} />);
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("hello");
    expect(marks[0].className).toBe("chatSearchActive");
  });

  it("applies active class correctly across text and code blocks", () => {
    const md = ["hello text", "", "```", "hello code", "```", "", "hello more"].join("\n");
    const { container } = render(<ChatMarkdownBlock content={md} searchQuery="hello" activeOccurrenceIndex={1} />);
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(3);
    expect(marks[0].className).toBe("chatSearchMatch");
    expect(marks[1].className).toBe("chatSearchActive");
    expect(marks[2].className).toBe("chatSearchMatch");
  });

  // Clickable file paths

  describe("clickable file paths", () => {
    beforeEach(() => {
      mockOpenFileViewTab.mockClear();
    });

    it("renders inline code file path as clickable", () => {
      const { container } = render(<ChatMarkdownBlock content="See `src/index.ts`" />);
      const link = container.querySelector('[role="link"]');
      expect(link).toBeTruthy();
      expect(link!.textContent).toBe("src/index.ts");
      // The code element should be inside the clickable span
      expect(link!.querySelector("code")).toBeTruthy();
    });

    it("does not make non-path inline code clickable", () => {
      const { container } = render(<ChatMarkdownBlock content="Use `const x = 1` here" />);
      expect(container.querySelector('[role="link"]')).toBeNull();
    });

    it("renders plain text file path in paragraph as clickable", () => {
      const { container } = render(<ChatMarkdownBlock content="Edited src/foo.py successfully" />);
      const link = container.querySelector('[role="link"]');
      expect(link).toBeTruthy();
      expect(link!.textContent).toBe("src/foo.py");
    });

    it("renders plain text file path in list item as clickable", () => {
      const md = ["- src/a.py", "- src/b.ts"].join("\n");
      const { container } = render(<ChatMarkdownBlock content={md} />);
      const links = container.querySelectorAll('[role="link"]');
      expect(links).toHaveLength(2);
      expect(links[0].textContent).toBe("src/a.py");
      expect(links[1].textContent).toBe("src/b.ts");
    });

    it("does not make paths in fenced code blocks clickable", () => {
      const md = "```\nsrc/index.ts\n```";
      const { container } = render(<ChatMarkdownBlock content={md} />);
      // Fenced code blocks should not contain role=link elements
      const pre = container.querySelector("pre");
      expect(pre).toBeTruthy();
      expect(pre!.querySelector('[role="link"]')).toBeNull();
    });

    it("calls openFileViewTab with correct args when clicked", () => {
      const { container } = render(<ChatMarkdownBlock content="See `src/index.ts`" />);
      const link = container.querySelector('[role="link"]');
      expect(link).toBeTruthy();
      fireEvent.click(link!);
      expect(mockOpenFileViewTab).toHaveBeenCalledWith({
        workspaceId: "test-ws",
        filePath: "src/index.ts",
      });
    });

    it("stops click propagation", () => {
      const parentSpy = vi.fn();
      const { container } = render(
        <div onClick={parentSpy} role="presentation">
          <ChatMarkdownBlock content="See `src/index.ts`" />
        </div>,
      );
      const link = container.querySelector('[role="link"]');
      expect(link).toBeTruthy();
      fireEvent.click(link!);
      expect(parentSpy).not.toHaveBeenCalled();
    });

    it("suppresses file links when enableFileLinks is false", () => {
      const { container } = render(<ChatMarkdownBlock content="See `src/index.ts`" enableFileLinks={false} />);
      expect(container.querySelector('[role="link"]')).toBeNull();
    });

    it("strips line number from navPath when clicking", () => {
      const { container } = render(<ChatMarkdownBlock content="See `src/file.py:42`" />);
      const link = container.querySelector('[role="link"]');
      expect(link).toBeTruthy();
      expect(link!.textContent).toBe("src/file.py:42");
      fireEvent.click(link!);
      expect(mockOpenFileViewTab).toHaveBeenCalledWith({
        workspaceId: "test-ws",
        filePath: "src/file.py",
      });
    });

    it("renders multiple occurrences as independent clickable links", () => {
      const md = "Changed src/a.py and src/a.py again";
      const { container } = render(<ChatMarkdownBlock content={md} />);
      const links = container.querySelectorAll('[role="link"]');
      expect(links).toHaveLength(2);
    });

    it("triggers navigation on Enter key press", () => {
      const { container } = render(<ChatMarkdownBlock content="See `src/index.ts`" />);
      const link = container.querySelector('[role="link"]');
      expect(link).toBeTruthy();
      fireEvent.keyDown(link!, { key: "Enter" });
      expect(mockOpenFileViewTab).toHaveBeenCalledWith({
        workspaceId: "test-ws",
        filePath: "src/index.ts",
      });
    });

    it("triggers navigation on Space key press", () => {
      const { container } = render(<ChatMarkdownBlock content="See `src/index.ts`" />);
      const link = container.querySelector('[role="link"]');
      expect(link).toBeTruthy();
      fireEvent.keyDown(link!, { key: " " });
      expect(mockOpenFileViewTab).toHaveBeenCalledWith({
        workspaceId: "test-ws",
        filePath: "src/index.ts",
      });
    });

    it("does not trigger navigation on other keys", () => {
      const { container } = render(<ChatMarkdownBlock content="See `src/index.ts`" />);
      const link = container.querySelector('[role="link"]');
      expect(link).toBeTruthy();
      fireEvent.keyDown(link!, { key: "Escape" });
      fireEvent.keyDown(link!, { key: "Tab" });
      fireEvent.keyDown(link!, { key: "a" });
      expect(mockOpenFileViewTab).not.toHaveBeenCalled();
    });

    it("suppresses file links when searchQuery is active", () => {
      const { container } = render(<ChatMarkdownBlock content="Updated src/foo.py with changes" searchQuery="src" />);
      // When searching, file paths in paragraphs should NOT be clickable
      expect(container.querySelector('[role="link"]')).toBeNull();
      // But search highlights should be present
      const marks = container.querySelectorAll("mark");
      expect(marks.length).toBeGreaterThan(0);
    });

    it("renders multiple inline code file paths in one paragraph", () => {
      const md = "See `src/a.ts` and `src/b.py` for details";
      const { container } = render(<ChatMarkdownBlock content={md} />);
      const links = container.querySelectorAll('[role="link"]');
      expect(links).toHaveLength(2);
      expect(links[0].textContent).toBe("src/a.ts");
      expect(links[1].textContent).toBe("src/b.py");
    });

    it("strips workspace prefix from absolute paths in inline code", () => {
      render(<ChatMarkdownBlock content="See `/mock/workspace/code/src/index.ts`" />);
      const link = screen.getByRole("link");
      expect(link).toBeTruthy();
      fireEvent.click(link);
      expect(mockOpenFileViewTab).toHaveBeenCalledWith({
        workspaceId: "test-ws",
        filePath: "src/index.ts",
      });
    });

    it("keyboard Enter on plain text file path triggers navigation", () => {
      const { container } = render(<ChatMarkdownBlock content="Edited src/foo.py successfully" />);
      const link = container.querySelector('[role="link"]');
      expect(link).toBeTruthy();
      fireEvent.keyDown(link!, { key: "Enter" });
      expect(mockOpenFileViewTab).toHaveBeenCalledWith({
        workspaceId: "test-ws",
        filePath: "src/foo.py",
      });
    });

    it("has tabIndex=0 for keyboard focus", () => {
      const { container } = render(<ChatMarkdownBlock content="See `src/index.ts`" />);
      const link = container.querySelector('[role="link"]');
      expect(link).toBeTruthy();
      expect(link!.getAttribute("tabindex")).toBe("0");
    });

    it("does not make inline code absolute path outside workspace clickable", () => {
      const { container } = render(<ChatMarkdownBlock content="See `/etc/config.yaml` for info" />);
      expect(container.querySelector('[role="link"]')).toBeNull();
      // Should still render as inline code
      const code = container.querySelector("code");
      expect(code).toBeTruthy();
      expect(code!.textContent).toBe("/etc/config.yaml");
    });

    it("does not make plain text absolute path outside workspace clickable", () => {
      const { container } = render(<ChatMarkdownBlock content="See /etc/config.yaml for info" />);
      expect(container.querySelector('[role="link"]')).toBeNull();
    });

    it("only linkifies in-workspace path when mixed with out-of-workspace path", () => {
      const md = "See `/mock/workspace/code/src/a.py` and `/etc/config.yaml`";
      const { container } = render(<ChatMarkdownBlock content={md} />);
      const links = container.querySelectorAll('[role="link"]');
      expect(links).toHaveLength(1);
      expect(links[0].textContent).toBe("/mock/workspace/code/src/a.py");
    });
  });

  // showCursor prop

  describe("showCursor", () => {
    const cursorSelector = `[data-testid="${ElementIds.STREAMING_CURSOR}"]`;

    it("does not inject cursor by default", () => {
      const { container } = render(<ChatMarkdownBlock content="Hello world" />);
      expect(container.querySelector(cursorSelector)).toBeNull();
    });

    it("does not inject cursor when showCursor is false", () => {
      const { container } = render(<ChatMarkdownBlock content="Hello world" showCursor={false} />);
      expect(container.querySelector(cursorSelector)).toBeNull();
    });

    it("injects cursor span when showCursor is true", () => {
      const { container } = render(<ChatMarkdownBlock content="Hello world" showCursor={true} />);
      expect(container.querySelector(cursorSelector)).toBeTruthy();
    });

    it("places cursor inside the last paragraph", () => {
      const { container } = render(<ChatMarkdownBlock content="Hello world" showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor?.parentElement?.tagName).toBe("P");
    });

    it("still renders markdown content correctly when showCursor is true", () => {
      const { container } = render(<ChatMarkdownBlock content="**bold** text" showCursor={true} />);
      expect(container.querySelector("strong")).toBeTruthy();
      expect(container.querySelector("strong")!.textContent).toBe("bold");
      expect(container.querySelector(cursorSelector)).toBeTruthy();
    });

    it("places cursor inside heading", () => {
      const { container } = render(<ChatMarkdownBlock content="# Heading" showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor?.parentElement?.tagName).toBe("H1");
    });

    it("places cursor inside last list item", () => {
      const md = ["- Item 1", "- Item 2"].join("\n");
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor?.parentElement?.tagName).toBe("LI");
      expect(cursor?.parentElement?.textContent).toContain("Item 2");
    });

    it("places cursor inside blockquote", () => {
      const { container } = render(<ChatMarkdownBlock content="> A quote" showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor).toBeTruthy();
      expect(cursor!.closest("blockquote")).toBeTruthy();
    });

    it("places cursor after code block (not inside pre)", () => {
      const md = "```\nconst x = 1;\n```";
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor).toBeTruthy();
      // Code blocks are replaced by ChatCodeBlock, so cursor is appended at the container level
      expect(cursor!.closest("pre")).toBeNull();
    });

    it("places cursor inside last table cell", () => {
      const md = "| A | B |\n|---|---|\n| 1 | 2 |";
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor).toBeTruthy();
      expect(cursor!.parentElement?.tagName).toBe("TD");
    });

    it("places cursor in container when last element is hr", () => {
      const md = "Some text\n\n---";
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor).toBeTruthy();
      // HR is void, so cursor should be appended to the container div, not inside the HR
      expect(cursor!.parentElement?.tagName).not.toBe("HR");
    });

    it("removes cursor when showCursor changes to false", () => {
      const { container, rerender } = render(<ChatMarkdownBlock content="Hello" showCursor={true} />);
      expect(container.querySelector(cursorSelector)).toBeTruthy();
      rerender(<ChatMarkdownBlock content="Hello" showCursor={false} />);
      expect(container.querySelector(cursorSelector)).toBeNull();
    });

    it("repositions cursor when content changes while showCursor is true", () => {
      const { container, rerender } = render(<ChatMarkdownBlock content="First paragraph" showCursor={true} />);
      const cursor1 = container.querySelector(cursorSelector);
      expect(cursor1).toBeTruthy();
      expect(cursor1?.parentElement?.tagName).toBe("P");

      // Change content to a list — cursor should move to the last list item
      rerender(<ChatMarkdownBlock content="- Item A\n- Item B" showCursor={true} />);
      const cursor2 = container.querySelector(cursorSelector);
      expect(cursor2).toBeTruthy();
      expect(cursor2?.parentElement?.tagName).toBe("LI");
      expect(cursor2?.parentElement?.textContent).toContain("Item B");
    });

    it("only injects a single cursor element", () => {
      const md = "Paragraph one.\n\nParagraph two.\n\nParagraph three.";
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursors = container.querySelectorAll(cursorSelector);
      expect(cursors).toHaveLength(1);
    });

    it("places cursor inside nested blockquote", () => {
      const md = "> outer\n> \n> > inner quote";
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor).toBeTruthy();
      expect(cursor!.closest("blockquote")).toBeTruthy();
      // Cursor should be in the innermost blockquote's paragraph
      const innerBq = container.querySelector("blockquote blockquote");
      expect(innerBq).toBeTruthy();
      expect(innerBq!.querySelector(cursorSelector)).toBeTruthy();
    });

    it("places cursor inside ordered list last item", () => {
      const md = "1. First\n2. Second\n3. Third";
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor?.parentElement?.tagName).toBe("LI");
      expect(cursor?.parentElement?.textContent).toContain("Third");
    });

    it("places cursor inside last paragraph when content has mixed elements", () => {
      const md = "# Heading\n\nSome text\n\n- list item\n\nFinal paragraph";
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor?.parentElement?.tagName).toBe("P");
      expect(cursor?.parentElement?.textContent).toContain("Final paragraph");
    });

    it("places cursor in last h2 heading", () => {
      const md = "## First Heading\n\n## Second Heading";
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor?.parentElement?.tagName).toBe("H2");
      expect(cursor?.parentElement?.textContent).toContain("Second Heading");
    });

    it("places cursor correctly for h3 through h6 headings", () => {
      for (const [level, prefix] of [
        [3, "###"],
        [4, "####"],
        [5, "#####"],
        [6, "######"],
      ] as const) {
        cleanup();
        const { container } = render(<ChatMarkdownBlock content={`${prefix} Heading`} showCursor={true} />);
        const cursor = container.querySelector(cursorSelector);
        expect(cursor?.parentElement?.tagName).toBe(`H${level}`);
      }
    });

    it("places cursor in table cell when table is last element after text", () => {
      const md = "Some intro text\n\n| A | B |\n|---|---|\n| 1 | 2 |";
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor).toBeTruthy();
      expect(cursor!.parentElement?.tagName).toBe("TD");
    });

    it("handles content with only a code block", () => {
      const md = "```python\nx = 1\n```";
      const { container } = render(<ChatMarkdownBlock content={md} showCursor={true} />);
      const cursor = container.querySelector(cursorSelector);
      expect(cursor).toBeTruthy();
    });

    it("cursor does not duplicate on rapid content updates", () => {
      const { container, rerender } = render(<ChatMarkdownBlock content="A" showCursor={true} />);
      rerender(<ChatMarkdownBlock content="AB" showCursor={true} />);
      rerender(<ChatMarkdownBlock content="ABC" showCursor={true} />);
      rerender(<ChatMarkdownBlock content="ABCD" showCursor={true} />);
      const cursors = container.querySelectorAll(cursorSelector);
      expect(cursors).toHaveLength(1);
    });

    it("cursor is removed on unmount", () => {
      const { container, unmount } = render(<ChatMarkdownBlock content="Hello" showCursor={true} />);
      expect(container.querySelector(cursorSelector)).toBeTruthy();
      unmount();
      // After unmount, the container is empty
      expect(container.querySelector(cursorSelector)).toBeNull();
    });
  });

  // Tiptap serializes inserted mentions as `<span data-sculptor-node ...>…</span>`
  // in the message text. ChatMarkdownBlock must turn those wrappers back into
  // styled chips (matching the editor), not leak them as raw HTML text.
  describe("sculptor-node span rendering", () => {
    const skillSpan = (name: string, description = "", type = ""): string => {
      const descAttr = description ? ` data-skill-description="${description}"` : "";
      const typeAttr = type ? ` data-skill-type="${type}"` : "";
      return `<span data-sculptor-node${descAttr}${typeAttr}>${name}</span>`;
    };
    const fileSpan = (path: string): string => `<span data-sculptor-node>${path}</span>`;

    it("renders a single /skill chip as a MENTION_SPAN", () => {
      const content = skillSpan("/linear", "Interact with Linear tickets", "custom");
      const { container } = render(<ChatMarkdownBlock content={content} enableFileLinks={false} />);
      const chips = container.querySelectorAll(`[data-testid="${ElementIds.MENTION_SPAN}"]`);
      expect(chips).toHaveLength(1);
      expect(chips[0].textContent).toBe("/linear");
      // The raw HTML wrapper must not leak through as visible text.
      expect(container.textContent).not.toContain("data-sculptor-node");
    });

    it("renders a file @-mention chip showing only the basename", () => {
      const content = fileSpan("@src/helpers.py");
      const { container } = render(<ChatMarkdownBlock content={content} enableFileLinks={false} />);
      const chips = container.querySelectorAll(`[data-testid="${ElementIds.MENTION_SPAN}"]`);
      expect(chips).toHaveLength(1);
      // Matches MentionNodeView's behavior: chip shows the basename, not the full path.
      expect(chips[0].textContent).toBe("helpers.py");
      expect(container.textContent).not.toContain("data-sculptor-node");
    });

    it("renders a directory @-mention chip showing the folder basename", () => {
      const content = fileSpan("@.claude/hooks/");
      const { container } = render(<ChatMarkdownBlock content={content} enableFileLinks={false} />);
      const chips = container.querySelectorAll(`[data-testid="${ElementIds.MENTION_SPAN}"]`);
      expect(chips).toHaveLength(1);
      expect(chips[0].textContent).toBe("hooks");
      expect(container.textContent).not.toContain("data-sculptor-node");
    });

    it("renders multiple adjacent chips of mixed types without markdown-escaping the sentinels", () => {
      // Regression: the sentinel originally used `_` as a delimiter (e.g.
      // `+[sculptorChip:0|_]`), which remark-gfm pair-matched as italic
      // markers across adjacent sentinels and broke multi-chip messages.
      const content = [
        fileSpan("@.claude/"),
        fileSpan("@README.md"),
        skillSpan("/address-comments", "Apply PR review comments", "custom"),
      ].join(" ");

      const { container } = render(<ChatMarkdownBlock content={content} enableFileLinks={false} />);

      const chips = container.querySelectorAll(`[data-testid="${ElementIds.MENTION_SPAN}"]`);
      expect(chips).toHaveLength(3);
      expect(chips[0].textContent).toBe(".claude");
      expect(chips[1].textContent).toBe("README.md");
      expect(chips[2].textContent).toBe("/address-comments");

      // No leftover sentinel text, no leftover HTML wrappers, no italicized
      // sentinel remnants (which is how the old bug surfaced).
      expect(container.textContent).not.toContain("sculptorChip");
      expect(container.textContent).not.toContain("data-sculptor-node");
      expect(container.querySelector("em")).toBeNull();
    });

    it("renders chips interleaved with regular text", () => {
      const content = `Please check ${fileSpan("@README.md")} and run ${skillSpan("/test-unit")}.`;
      const { container } = render(<ChatMarkdownBlock content={content} enableFileLinks={false} />);
      const chips = container.querySelectorAll(`[data-testid="${ElementIds.MENTION_SPAN}"]`);
      expect(chips).toHaveLength(2);
      // The surrounding prose is preserved verbatim.
      expect(container.textContent).toContain("Please check");
      expect(container.textContent).toContain("and run");
      expect(container.textContent).toContain(".");
    });
  });
});
