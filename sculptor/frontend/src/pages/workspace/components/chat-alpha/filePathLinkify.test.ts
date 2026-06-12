import { describe, expect, it } from "vitest";

import type { Segment } from "./filePathLinkify.ts";
import {
  isFilePath,
  isPathInWorkspace,
  resolveNavPath,
  splitFilePathSegments,
  stripLineNumber,
} from "./filePathLinkify.ts";

// ---------------------------------------------------------------------------
// isFilePath
// ---------------------------------------------------------------------------

describe("isFilePath", () => {
  it("detects relative paths", () => {
    expect(isFilePath("src/index.ts")).toBe(true);
    expect(isFilePath("sculptor/sculptor/constants.py")).toBe(true);
    expect(isFilePath("src/index.tsx")).toBe(true);
    expect(isFilePath("path/to/file.json")).toBe(true);
  });

  it("detects absolute paths", () => {
    expect(isFilePath("/Users/foo/project/file.py")).toBe(true);
    expect(isFilePath("/home/user/src/main.rs")).toBe(true);
  });

  it("detects paths with line numbers", () => {
    expect(isFilePath("src/file.py:42")).toBe(true);
    expect(isFilePath("/Users/foo/project/file.py:100")).toBe(true);
  });

  it("rejects bare filenames without /", () => {
    expect(isFilePath("constants.py")).toBe(false);
    expect(isFilePath("index.ts")).toBe(false);
  });

  it("rejects empty and non-path strings", () => {
    expect(isFilePath("")).toBe(false);
    expect(isFilePath("hello world")).toBe(false);
    expect(isFilePath("const x = 1")).toBe(false);
  });

  it("rejects URLs", () => {
    expect(isFilePath("https://example.com/page")).toBe(false);
    expect(isFilePath("https://example.com/page.html")).toBe(false);
    expect(isFilePath("http://example.com/file.js")).toBe(false);
    expect(isFilePath("ftp://server.com/file.txt")).toBe(false);
  });

  it("rejects paths without a known extension", () => {
    expect(isFilePath("path/to/Makefile")).toBe(false);
    expect(isFilePath("src/binary")).toBe(false);
  });

  it("handles whitespace-trimmed input", () => {
    expect(isFilePath("  src/index.ts  ")).toBe(true);
  });

  it("detects paths with tilde and dotfile directories", () => {
    expect(isFilePath("~/.config/app.toml")).toBe(true);
    expect(isFilePath(".github/workflows/ci.yml")).toBe(true);
    expect(isFilePath("src/.hidden/config.json")).toBe(true);
  });

  it("distinguishes similar extensions correctly", () => {
    expect(isFilePath("src/main.c")).toBe(true);
    expect(isFilePath("src/main.cpp")).toBe(true);
    expect(isFilePath("src/style.css")).toBe(true);
    expect(isFilePath("src/style.scss")).toBe(true);
    expect(isFilePath("src/file.ts")).toBe(true);
    expect(isFilePath("src/file.tsx")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// stripLineNumber
// ---------------------------------------------------------------------------

describe("stripLineNumber", () => {
  it("strips trailing :digits", () => {
    expect(stripLineNumber("file.py:42")).toBe("file.py");
    expect(stripLineNumber("file.py:0")).toBe("file.py");
  });

  it("returns path as-is without line number", () => {
    expect(stripLineNumber("file.py")).toBe("file.py");
  });

  it("only strips the last :digits segment", () => {
    expect(stripLineNumber("file.py:123:456")).toBe("file.py:123");
  });
});

// ---------------------------------------------------------------------------
// resolveNavPath
// ---------------------------------------------------------------------------

describe("resolveNavPath", () => {
  const workspaceCodePath = "/mock/workspace/code";

  it("strips workspace prefix from absolute paths", () => {
    expect(resolveNavPath("/mock/workspace/code/src/index.ts", workspaceCodePath)).toBe("src/index.ts");
  });

  it("strips workspace prefix and line number", () => {
    expect(resolveNavPath("/mock/workspace/code/src/index.ts:42", workspaceCodePath)).toBe("src/index.ts");
  });

  it("returns absolute path as-is if prefix does not match", () => {
    expect(resolveNavPath("/other/path/file.py", workspaceCodePath)).toBe("/other/path/file.py");
  });

  it("returns relative path as-is", () => {
    expect(resolveNavPath("src/index.ts", workspaceCodePath)).toBe("src/index.ts");
  });

  it("strips line number from relative path", () => {
    expect(resolveNavPath("src/index.ts:42", workspaceCodePath)).toBe("src/index.ts");
  });

  it("handles null workspaceCodePath", () => {
    expect(resolveNavPath("src/index.ts:42", null)).toBe("src/index.ts");
    expect(resolveNavPath("/abs/path/file.py", null)).toBe("/abs/path/file.py");
  });

  it("handles workspaceCodePath with trailing slash", () => {
    expect(resolveNavPath("/mock/workspace/code/src/a.ts", "/mock/workspace/code/")).toBe("src/a.ts");
  });
});

// ---------------------------------------------------------------------------
// isPathInWorkspace
// ---------------------------------------------------------------------------

describe("isPathInWorkspace", () => {
  const workspaceCodePath = "/mock/workspace/code";

  it("accepts relative paths", () => {
    expect(isPathInWorkspace("src/index.ts", workspaceCodePath)).toBe(true);
    expect(isPathInWorkspace("src/index.ts:42", workspaceCodePath)).toBe(true);
  });

  it("accepts absolute paths inside the workspace", () => {
    expect(isPathInWorkspace("/mock/workspace/code/src/index.ts", workspaceCodePath)).toBe(true);
  });

  it("rejects absolute paths outside the workspace", () => {
    expect(isPathInWorkspace("/etc/config.yaml", workspaceCodePath)).toBe(false);
    expect(isPathInWorkspace("/Users/foo/other/file.py", workspaceCodePath)).toBe(false);
  });

  it("rejects absolute paths when workspaceCodePath is null", () => {
    expect(isPathInWorkspace("/some/abs/path.py", null)).toBe(false);
  });

  it("accepts relative paths when workspaceCodePath is null", () => {
    expect(isPathInWorkspace("src/index.ts", null)).toBe(true);
  });

  it("handles workspaceCodePath with trailing slash", () => {
    expect(isPathInWorkspace("/mock/workspace/code/src/a.ts", "/mock/workspace/code/")).toBe(true);
  });

  it("accepts absolute path with line number inside workspace", () => {
    expect(isPathInWorkspace("/mock/workspace/code/src/index.ts:42", workspaceCodePath)).toBe(true);
  });

  it("rejects absolute path with line number outside workspace", () => {
    expect(isPathInWorkspace("/etc/config.yaml:10", workspaceCodePath)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// splitFilePathSegments
// ---------------------------------------------------------------------------

describe("splitFilePathSegments", () => {
  it("returns single text segment for plain text", () => {
    const result = splitFilePathSegments("no paths here", null);
    expect(result).toEqual<ReadonlyArray<Segment>>([{ kind: "text", value: "no paths here" }]);
  });

  it("returns single path segment for a standalone path", () => {
    const result = splitFilePathSegments("src/index.ts", null);
    expect(result).toEqual<ReadonlyArray<Segment>>([{ kind: "path", value: "src/index.ts", navPath: "src/index.ts" }]);
  });

  it("splits text before and after a path", () => {
    const result = splitFilePathSegments("Edited src/index.ts successfully", null);
    expect(result).toEqual<ReadonlyArray<Segment>>([
      { kind: "text", value: "Edited " },
      { kind: "path", value: "src/index.ts", navPath: "src/index.ts" },
      { kind: "text", value: " successfully" },
    ]);
  });

  it("detects multiple paths in one string", () => {
    const result = splitFilePathSegments("Changed src/a.py and src/b.py", null);
    expect(result).toHaveLength(4);
    expect(result[0]).toEqual({ kind: "text", value: "Changed " });
    expect(result[1]).toEqual({ kind: "path", value: "src/a.py", navPath: "src/a.py" });
    expect(result[2]).toEqual({ kind: "text", value: " and " });
    expect(result[3]).toEqual({ kind: "path", value: "src/b.py", navPath: "src/b.py" });
  });

  it("handles same path appearing twice", () => {
    const result = splitFilePathSegments("src/a.py then src/a.py", null);
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(2);
  });

  it("preserves line number in display but strips for navPath", () => {
    const result = splitFilePathSegments("See src/file.py:42", null);
    expect(result).toEqual<ReadonlyArray<Segment>>([
      { kind: "text", value: "See " },
      { kind: "path", value: "src/file.py:42", navPath: "src/file.py" },
    ]);
  });

  it("detects path in parentheses", () => {
    const result = splitFilePathSegments("(src/foo.ts)", null);
    expect(result).toEqual<ReadonlyArray<Segment>>([
      { kind: "text", value: "(" },
      { kind: "path", value: "src/foo.ts", navPath: "src/foo.ts" },
      { kind: "text", value: ")" },
    ]);
  });

  it("detects comma-separated paths", () => {
    const result = splitFilePathSegments("src/a.py, src/b.py", null);
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(2);
    expect(pathSegments[0]).toEqual({ kind: "path", value: "src/a.py", navPath: "src/a.py" });
    expect(pathSegments[1]).toEqual({ kind: "path", value: "src/b.py", navPath: "src/b.py" });
  });

  it("resolves absolute paths with workspace prefix", () => {
    const result = splitFilePathSegments("Edited /ws/code/src/a.ts", "/ws/code");
    expect(result).toEqual<ReadonlyArray<Segment>>([
      { kind: "text", value: "Edited " },
      { kind: "path", value: "/ws/code/src/a.ts", navPath: "src/a.ts" },
    ]);
  });

  it("does not match URLs", () => {
    const result = splitFilePathSegments("Visit https://example.com/page.html for docs", null);
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(0);
  });

  it("handles empty string", () => {
    const result = splitFilePathSegments("", null);
    expect(result).toEqual<ReadonlyArray<Segment>>([{ kind: "text", value: "" }]);
  });

  it("skips absolute paths outside the workspace", () => {
    const result = splitFilePathSegments("See /Users/foo/project/file.py", null);
    expect(result).toEqual<ReadonlyArray<Segment>>([{ kind: "text", value: "See /Users/foo/project/file.py" }]);
  });

  it("linkifies absolute paths inside the workspace", () => {
    const result = splitFilePathSegments("See /ws/code/src/file.py", "/ws/code");
    expect(result).toEqual<ReadonlyArray<Segment>>([
      { kind: "text", value: "See " },
      { kind: "path", value: "/ws/code/src/file.py", navPath: "src/file.py" },
    ]);
  });

  it("detects paths followed by sentence-ending punctuation", () => {
    for (const punct of [".", "!", "?"]) {
      const result = splitFilePathSegments(`Updated src/foo.ts${punct}`, null);
      const pathSegments = result.filter((s) => s.kind === "path");
      expect(pathSegments).toHaveLength(1);
      expect(pathSegments[0].value).toBe("src/foo.ts");
    }
  });

  it("detects paths followed by semicolon or colon", () => {
    const result = splitFilePathSegments("Check src/foo.ts; also src/bar.py:", null);
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(2);
  });

  it("detects paths with tilde in directory names", () => {
    const result = splitFilePathSegments("See ~/.config/app.toml for config", null);
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(1);
    expect(pathSegments[0].value).toBe("~/.config/app.toml");
  });

  it("detects paths with dots in directory names", () => {
    const result = splitFilePathSegments("Edit src/my.config/settings.json", null);
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(1);
    expect(pathSegments[0].value).toBe("src/my.config/settings.json");
  });

  it("detects paths inside square brackets", () => {
    const result = splitFilePathSegments("[src/foo.ts]", null);
    expect(result).toEqual<ReadonlyArray<Segment>>([
      { kind: "text", value: "[" },
      { kind: "path", value: "src/foo.ts", navPath: "src/foo.ts" },
      { kind: "text", value: "]" },
    ]);
  });

  it("distinguishes .c from .cpp extensions", () => {
    const result = splitFilePathSegments("src/main.c and src/helper.cpp", null);
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(2);
    expect(pathSegments[0].value).toBe("src/main.c");
    expect(pathSegments[1].value).toBe("src/helper.cpp");
  });

  it("distinguishes .css from .scss extensions", () => {
    const result = splitFilePathSegments("src/style.css and src/theme.scss", null);
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(2);
    expect(pathSegments[0].value).toBe("src/style.css");
    expect(pathSegments[1].value).toBe("src/theme.scss");
  });

  it("does not match paths embedded in a URL after ://", () => {
    const result = splitFilePathSegments("Visit https://github.com/org/repo/blob/main/src/index.ts for docs", null);
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(0);
  });

  it("detects a path at the very start of the string", () => {
    const result = splitFilePathSegments("src/index.ts was updated", null);
    expect(result[0]).toEqual({ kind: "path", value: "src/index.ts", navPath: "src/index.ts" });
  });

  it("detects a path at the very end of the string", () => {
    const result = splitFilePathSegments("Updated src/index.ts", null);
    const last = result[result.length - 1];
    expect(last).toEqual({ kind: "path", value: "src/index.ts", navPath: "src/index.ts" });
  });

  it("detects paths with dotfile directories", () => {
    const result = splitFilePathSegments("See .github/workflows/ci.yml", null);
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(1);
    expect(pathSegments[0].value).toBe(".github/workflows/ci.yml");
  });

  it("linkifies only in-workspace path when mixed with out-of-workspace path", () => {
    const result = splitFilePathSegments("See /ws/code/src/a.py and /etc/config.yaml", "/ws/code");
    const pathSegments = result.filter((s) => s.kind === "path");
    expect(pathSegments).toHaveLength(1);
    expect(pathSegments[0]).toEqual({ kind: "path", value: "/ws/code/src/a.py", navPath: "src/a.py" });
    // The out-of-workspace path should be plain text
    const textSegments = result.filter((s) => s.kind === "text");
    expect(textSegments.some((s) => s.value.includes("/etc/config.yaml"))).toBe(true);
  });

  it("resolves absolute workspace path with line number", () => {
    const result = splitFilePathSegments("See /ws/code/src/a.ts:42", "/ws/code");
    expect(result).toEqual<ReadonlyArray<Segment>>([
      { kind: "text", value: "See " },
      { kind: "path", value: "/ws/code/src/a.ts:42", navPath: "src/a.ts" },
    ]);
  });
});
