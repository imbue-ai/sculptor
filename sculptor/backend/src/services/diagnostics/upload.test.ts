import { describe, expect, it } from "vitest";

import { uploadDiagnostics } from "~/services/diagnostics/upload";
import { createZip } from "~/services/diagnostics/zip";

describe("diagnostics upload (RW-PARITY-5 unsigned S3)", () => {
  it("PUTs the bundle unsigned to the report bucket and returns the report id + s3 url", async () => {
    const captured: { url: string; body: Buffer }[] = [];
    const putter = async (url: string, body: Buffer): Promise<void> => {
      captured.push({ url, body });
    };
    const now = new Date(
      "2026-06-24T10-20-30Z".replace(/-/g, ":").replace("T", "T"),
    );

    const result = await uploadDiagnostics(
      {
        description: "it broke",
        currentUrl: "http://localhost/x",
        frontendDiagnostics: { feature: "abc" },
      },
      { now: new Date("2026-06-24T10:20:30Z"), putter },
    );

    expect(captured).toHaveLength(1);
    const { url, body } = captured[0]!;
    // Same bucket/region/key scheme support expects.
    expect(url).toContain(
      "https://traceback-uploads-production.s3.us-west-2.amazonaws.com/error-reports/",
    );
    expect(url.endsWith(`${result.reportId}.zip`)).toBe(true);
    // The bundle is a real zip (PK magic) carrying the report.
    expect(body.subarray(0, 2).toString("latin1")).toBe("PK");
    // Response shape mirrors Python (report_id + s3_url).
    expect(result.s3Url).toBe(
      `s3://traceback-uploads-production/error-reports/${result.reportId}.zip`,
    );
    expect(result.reportId).toMatch(/^2026-06-24T10-20-30_/);
    expect(now).toBeInstanceOf(Date);
  });

  it("issues no signed/authenticated request (the putter receives no auth header path)", async () => {
    // The service hands the putter only (url, body) — there is no credential
    // resolution or Authorization header anywhere in the unsigned path.
    let calls = 0;
    await uploadDiagnostics(
      { description: "d", currentUrl: "u" },
      {
        now: new Date("2026-01-01T00:00:00Z"),
        putter: async () => {
          calls += 1;
        },
      },
    );
    expect(calls).toBe(1);
  });

  it("creates a valid multi-entry zip", () => {
    const zip = createZip([
      { name: "a.txt", data: Buffer.from("hello") },
      { name: "b/c.txt", data: Buffer.from("world") },
    ]);
    expect(zip.subarray(0, 4)).toEqual(Buffer.from([0x50, 0x4b, 0x03, 0x04]));
    // End-of-central-directory record present.
    expect(zip.includes(Buffer.from([0x50, 0x4b, 0x05, 0x06]))).toBe(true);
  });
});
