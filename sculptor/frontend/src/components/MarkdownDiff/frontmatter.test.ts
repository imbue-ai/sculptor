import { describe, expect, it } from "vitest";

import { parseFrontmatter } from "./frontmatter.ts";

describe("parseFrontmatter", () => {
  it("extracts a leading YAML block and strips it from the body", () => {
    const { frontmatter, body } = parseFrontmatter("---\ntitle: Doc\nauthor: Ada\n---\n\n# Heading\n\nBody\n");
    expect(frontmatter).not.toBeNull();
    expect(frontmatter?.lang).toBe("yaml");
    expect(frontmatter?.data).toEqual({ title: "Doc", author: "Ada" });
    expect(body).toBe("# Heading\n\nBody\n");
  });

  it("returns no frontmatter when the document doesn't start with a fence", () => {
    const content = "# Heading\n\n---\n\nA thematic break, not frontmatter.\n";
    const { frontmatter, body } = parseFrontmatter(content);
    expect(frontmatter).toBeNull();
    expect(body).toBe(content);
  });

  it("leaves a mid-document `---` thematic break untouched", () => {
    const { frontmatter, body } = parseFrontmatter("---\ntitle: Doc\n---\n\nIntro\n\n---\n\nMore\n");
    expect(frontmatter?.data).toEqual({ title: "Doc" });
    // The second `---` is a real horizontal rule and must survive in the body.
    expect(body).toBe("Intro\n\n---\n\nMore\n");
  });

  it("parses nested mappings, arrays, and multi-line block scalars", () => {
    const content = [
      "---",
      "name: tool",
      "tags:",
      "  - docs",
      "  - internal",
      "meta:",
      "  level: 2",
      "---",
      "Body",
    ].join("\n");
    const { frontmatter } = parseFrontmatter(content);
    expect(frontmatter?.data).toEqual({ name: "tool", tags: ["docs", "internal"], meta: { level: 2 } });
  });

  it("falls back to raw (data null) on malformed YAML rather than dropping it", () => {
    const { frontmatter, body } = parseFrontmatter("---\nkey: : : broken\n  bad indent\n---\nBody\n");
    expect(frontmatter).not.toBeNull();
    expect(frontmatter?.data).toBeNull();
    expect(frontmatter?.raw).toContain("broken");
    expect(body).toBe("Body\n");
  });

  it("treats a non-mapping scalar block as raw (data null)", () => {
    const { frontmatter } = parseFrontmatter("---\njust a string\n---\nBody\n");
    expect(frontmatter?.data).toBeNull();
    expect(frontmatter?.raw).toBe("just a string");
  });

  it("detects TOML (`+++`) fences, stripping but not parsing them yet", () => {
    const { frontmatter, body } = parseFrontmatter('+++\ntitle = "Doc"\n+++\n\nBody\n');
    expect(frontmatter?.lang).toBe("toml");
    expect(frontmatter?.data).toBeNull();
    expect(frontmatter?.raw).toBe('title = "Doc"');
    expect(body).toBe("Body\n");
  });

  it("handles CRLF line endings", () => {
    const { frontmatter, body } = parseFrontmatter("---\r\ntitle: Doc\r\n---\r\nBody\r\n");
    expect(frontmatter?.data).toEqual({ title: "Doc" });
    expect(body).toBe("Body\r\n");
  });

  it("tolerates a frontmatter block that is the entire file (no trailing body)", () => {
    const { frontmatter, body } = parseFrontmatter("---\ntitle: Doc\n---");
    expect(frontmatter?.data).toEqual({ title: "Doc" });
    expect(body).toBe("");
  });
});
