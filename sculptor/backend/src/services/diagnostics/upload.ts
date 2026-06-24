import { existsSync, readFileSync, statfsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";

import { logsDir } from "~/config/sculptor_folder";
import { createZip } from "~/services/diagnostics/zip";

// Unsigned S3 diagnostics upload (web/upload_diagnostics.py). The Python backend
// PUTs the bundle into a PUBLIC report bucket with UNSIGNED/anonymous access
// (botocore UNSIGNED) — there are no credentials, so a signed request would be
// rejected by the bucket policy. We reproduce that with a plain unauthenticated
// HTTPS PUT to the object URL: no Authorization/SigV4 header is sent.

const REPORT_BUCKET = "traceback-uploads-production";
const REPORT_S3_PREFIX = "error-reports";
const REPORT_REGION = "us-west-2";

const BYTES_PER_GIBIBYTE = 1024 ** 3;

export interface UploadDiagnosticsRequest {
  description: string;
  currentUrl: string;
  frontendDiagnostics?: Record<string, string | number | null>;
}

export interface UploadDiagnosticsResponse {
  reportId: string;
  s3Url: string;
}

// An unsigned HTTP PUT of the bundle. Injected so tests can assert the request
// carries no auth and targets the right URL without hitting the network.
export type DiagnosticsPutter = (url: string, body: Buffer) => Promise<void>;

const defaultPutter: DiagnosticsPutter = async (url, body) => {
  const response = await fetch(url, {
    method: "PUT",
    body,
    headers: { "Content-Type": "application/zip" },
  });
  if (!response.ok) {
    throw new Error(
      `Diagnostics upload failed: ${response.status} ${response.statusText}`,
    );
  }
};

function freeDiskGb(): number | null {
  try {
    const stats = statfsSync(os.homedir());
    return Math.round((stats.bavail * stats.bsize) / BYTES_PER_GIBIBYTE) || 0;
  } catch {
    return null;
  }
}

function collectServerDiagnostics(): Record<string, string | number | null> {
  return {
    platform: os.platform(),
    platform_version: os.release(),
    node_version: process.versions.node,
    free_disk_gb: freeDiskGb(),
  };
}

function buildReportMarkdown(
  reportId: string,
  now: Date,
  description: string,
  currentUrl: string,
  diagnostics: Record<string, string | number | null>,
): string {
  const diagnosticsBlock = Object.entries(diagnostics)
    .filter(([, value]) => value !== null)
    .map(([key, value]) => `- **${key}**: ${value}`)
    .join("\n");
  return [
    `**Report ID**: \`${reportId}\`\n**Date**: ${now.toISOString()}\n**URL**: ${currentUrl}`,
    `## Description\n\n${description}`,
    `## Diagnostics\n\n${diagnosticsBlock}`,
  ].join("\n\n");
}

export interface UploadDiagnosticsOptions {
  now?: Date;
  putter?: DiagnosticsPutter;
}

// Bundle diagnostics + logs into a zip and upload it unsigned. Returns the
// report id + the s3:// URL (the same bucket/key scheme support expects).
export async function uploadDiagnostics(
  request: UploadDiagnosticsRequest,
  options: UploadDiagnosticsOptions = {},
): Promise<UploadDiagnosticsResponse> {
  const now = options.now ?? new Date();
  const putter = options.putter ?? defaultPutter;
  const timestamp = now.toISOString().slice(0, 19).replace(/:/g, "-");
  const reportId = `${timestamp}_${randomUUID()}`;
  const s3Key = `${REPORT_S3_PREFIX}/${reportId}.zip`;

  const diagnostics: Record<string, string | number | null> =
    collectServerDiagnostics();
  for (const [key, value] of Object.entries(
    request.frontendDiagnostics ?? {},
  )) {
    diagnostics[`frontend.${key}`] = value;
  }

  const markdown = buildReportMarkdown(
    reportId,
    now,
    request.description,
    request.currentUrl,
    diagnostics,
  );
  const entries: { name: string; data: Uint8Array }[] = [{ name: "report.md", data: Buffer.from(markdown, "utf8") }];

  const serverLog = path.join(logsDir(), "server", "logs.jsonl");
  if (existsSync(serverLog)) {
    entries.push({ name: "logs/server.jsonl", data: readFileSync(serverLog) });
  }
  const electronLog = path.join(logsDir(), "electron.log");
  if (existsSync(electronLog)) {
    entries.push({
      name: "logs/electron.log",
      data: readFileSync(electronLog),
    });
  }

  const zipBytes = createZip(entries);
  const url = `https://${REPORT_BUCKET}.s3.${REPORT_REGION}.amazonaws.com/${s3Key}`;
  await putter(url, zipBytes);

  return { reportId, s3Url: `s3://${REPORT_BUCKET}/${s3Key}` };
}
