import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { PostHog } from "posthog-node";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ensureSculptorFolderReady } from "~/config/bootstrap";
import {
  configPath,
  SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG,
} from "~/config/sculptor_folder";
import { TelemetryEvent } from "~/telemetry/events";
import {
  capture,
  maskProperties,
  resetTelemetryForTests,
} from "~/telemetry/posthog";

const TOKEN_ENV = "SCULPTOR_BACKEND_POSTHOG_TOKEN";

describe("maskProperties (REQ-SEC-010 masking)", () => {
  it("redacts private content but keeps non-private fields", () => {
    const masked = maskProperties({
      message: "secret user text",
      filePath: "/Users/dev/x",
      apiKey: "sk-123",
      count: 5,
      nested: { prompt: "hidden", ok: "kept" },
      items: [{ token: "t" }, { value: "v" }],
    }) as Record<string, unknown>;
    expect(masked.message).toBe("[redacted]");
    expect(masked.filePath).toBe("[redacted]");
    expect(masked.apiKey).toBe("[redacted]");
    expect(masked.count).toBe(5);
    expect((masked.nested as Record<string, unknown>).prompt).toBe(
      "[redacted]",
    );
    expect((masked.nested as Record<string, unknown>).ok).toBe("kept");
    expect((masked.items as Record<string, unknown>[])[0]!.token).toBe(
      "[redacted]",
    );
    expect((masked.items as Record<string, unknown>[])[1]!.value).toBe("v");
  });
});

describe("capture (REQ-SEC-010 consent gate)", () => {
  let dir: string;
  let previousFolder: string | undefined;
  let previousToken: string | undefined;
  let captureSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    previousToken = process.env[TOKEN_ENV];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-ph-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    process.env[TOKEN_ENV] = "phc_test_token";
    ensureSculptorFolderReady(process.env);
    resetTelemetryForTests();
    captureSpy = vi
      .spyOn(PostHog.prototype, "capture")
      .mockImplementation(() => undefined as never);
  });

  afterEach(() => {
    captureSpy.mockRestore();
    resetTelemetryForTests();
    if (previousFolder === undefined) {
      delete process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    } else {
      process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = previousFolder;
    }
    if (previousToken === undefined) {
      delete process.env[TOKEN_ENV];
    } else {
      process.env[TOKEN_ENV] = previousToken;
    }
    rmSync(dir, { recursive: true, force: true });
  });

  function setConsent(enabled: boolean): void {
    const value = enabled ? "true" : "false";
    writeFileSync(
      configPath(),
      `is_error_reporting_enabled = ${value}\nis_product_analytics_enabled = ${value}\n`,
    );
  }

  it("emits nothing when consent is not granted", () => {
    setConsent(false);
    capture(TelemetryEvent.FrontendTraceBatch, { message: "x" });
    expect(captureSpy).not.toHaveBeenCalled();
  });

  it("captures with masked properties when consent is granted", () => {
    setConsent(true);
    capture(TelemetryEvent.FrontendTraceBatch, { message: "x", count: 1 });
    expect(captureSpy).toHaveBeenCalledTimes(1);
    const arg = captureSpy.mock.calls[0]![0] as {
      event: string;
      properties: Record<string, unknown>;
    };
    expect(arg.event).toBe(TelemetryEvent.FrontendTraceBatch);
    expect(arg.properties.message).toBe("[redacted]");
    expect(arg.properties.count).toBe(1);
  });

  it("no-ops when no backend token is configured even with consent", () => {
    delete process.env[TOKEN_ENV];
    resetTelemetryForTests();
    setConsent(true);
    capture(TelemetryEvent.FrontendTraceBatch, { count: 1 });
    expect(captureSpy).not.toHaveBeenCalled();
  });
});
