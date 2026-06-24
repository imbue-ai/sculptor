import { describe, expect, it } from "vitest";

import { resolveClaudeBinary } from "~/harness/claude/launch";
import {
  AgentClientError,
  ClaudeBinaryNotFoundError,
  PiBinaryNotFoundError,
  PiVersionMismatchError,
  serializeError,
} from "~/harness/errors";
import { resolvePiBinary } from "~/harness/pi/launch";

describe("error taxonomy", () => {
  it("the binary-not-found errors are distinct AgentClientErrors with stable messages", () => {
    const claude = new ClaudeBinaryNotFoundError();
    const pi = new PiBinaryNotFoundError();
    expect(claude).toBeInstanceOf(AgentClientError);
    expect(pi).toBeInstanceOf(AgentClientError);
    expect(claude.name).toBe("ClaudeBinaryNotFoundError");
    expect(pi.name).toBe("PiBinaryNotFoundError");
    expect(claude.message).toBe("Claude binary not found or is invalid.");
    expect(pi.message).toBe("Pi binary not found or is invalid.");
  });

  it("serializes to the SerializedException shape the projection folds", () => {
    expect(serializeError(new ClaudeBinaryNotFoundError())).toEqual({
      exception: "ClaudeBinaryNotFoundError",
      args: ["Claude binary not found or is invalid."],
      traceback_dict: null,
    });
  });

  it("PiVersionMismatchError reports the detected + pinned versions", () => {
    const error = new PiVersionMismatchError("0.77.0", "0.78.0");
    expect(error.detectedVersion).toBe("0.77.0");
    expect(error.message).toContain("0.77.0");
    expect(error.message).toContain("0.78.0");
  });
});

describe("binary resolution", () => {
  it("returns the path when present and raises the specific error when absent", () => {
    expect(resolveClaudeBinary(() => "/bin/claude")).toBe("/bin/claude");
    expect(() => resolveClaudeBinary(() => undefined)).toThrow(
      ClaudeBinaryNotFoundError,
    );
    expect(resolvePiBinary(() => "/bin/pi")).toBe("/bin/pi");
    expect(() => resolvePiBinary(() => undefined)).toThrow(
      PiBinaryNotFoundError,
    );
  });
});
