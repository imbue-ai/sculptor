import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { resolveStaticAssetDir } from "~/config/paths";

describe("resolveStaticAssetDir", () => {
  let dir: string;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-paths-"));
    writeFileSync(path.join(dir, "index.html"), "<html></html>");
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("honors SCULPTOR_STATIC_DIR", () => {
    expect(resolveStaticAssetDir({ SCULPTOR_STATIC_DIR: dir } as NodeJS.ProcessEnv, "/nonexistent")).toBe(dir);
  });

  it("honors the harness STATIC_FILES_PATH", () => {
    expect(resolveStaticAssetDir({ STATIC_FILES_PATH: dir } as NodeJS.ProcessEnv, "/nonexistent")).toBe(dir);
  });

  it("returns undefined when no candidate contains index.html", () => {
    expect(resolveStaticAssetDir({} as NodeJS.ProcessEnv, "/nonexistent")).toBeUndefined();
  });
});
