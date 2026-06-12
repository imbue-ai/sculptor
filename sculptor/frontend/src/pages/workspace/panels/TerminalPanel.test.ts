import { describe, expect, it } from "vitest";

import { getNextTerminalLabel } from "./terminalLabelUtils";

describe("getNextTerminalLabel", () => {
  it("returns 'Terminal 1' when no tabs exist", () => {
    expect(getNextTerminalLabel([])).toBe("Terminal 1");
  });

  it("returns the next sequential number when all are present", () => {
    const tabs = [{ label: "Terminal 1" }, { label: "Terminal 2" }];
    expect(getNextTerminalLabel(tabs)).toBe("Terminal 3");
  });

  it("reuses the lowest available number after deletion", () => {
    const tabs = [{ label: "Terminal 2" }];
    expect(getNextTerminalLabel(tabs)).toBe("Terminal 1");
  });

  it("fills the gap when a middle terminal is deleted", () => {
    const tabs = [{ label: "Terminal 1" }, { label: "Terminal 3" }];
    expect(getNextTerminalLabel(tabs)).toBe("Terminal 2");
  });

  it("ignores renamed tabs when computing the next number", () => {
    const tabs = [{ label: "My Server" }, { label: "Terminal 2" }];
    expect(getNextTerminalLabel(tabs)).toBe("Terminal 1");
  });

  it("handles a mix of renamed and numbered tabs", () => {
    const tabs = [{ label: "Terminal 1" }, { label: "My Server" }, { label: "Terminal 3" }];
    expect(getNextTerminalLabel(tabs)).toBe("Terminal 2");
  });
});
