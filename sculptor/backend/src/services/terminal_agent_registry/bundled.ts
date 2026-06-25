import { copyFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { getRegistrationsDir } from "~/services/terminal_agent_registry/registry";

// Install the bundled Claude Code terminal-agent registration on first run.
// Sculptor ships `samples/terminal_agents/claude-code/` as both the reference
// example and a registration every user gets out of the box. At startup the two
// files are copied once into the registrations dir, where they become ordinary
// user-owned files: existing files are never overwritten, and a sentinel makes
// deleting them permanent (no re-install). Ports
// terminal_agent_registry/bundled.py install_bundled_registrations.

const SENTINEL_FILE_NAME = ".claude-code.installed";
const BUNDLED_FILE_NAMES = ["claude-code.toml", "claude-code-hooks.json"];

// Locate the shipped claude-code sample directory, or null. Probed relative to
// the working directory (like the migrations folder), covering a launch from
// the repo root or from sculptor/backend, plus the packaged `_internal/samples`.
function bundledClaudeCodeDir(cwd: string = process.cwd()): string | null {
  const relative = path.join("samples", "terminal_agents", "claude-code");
  const candidates = [
    path.resolve(cwd, relative),
    path.resolve(cwd, "sculptor", "backend", relative),
    path.resolve(cwd, "..", "..", relative),
    path.resolve(cwd, "_internal", relative),
  ];
  for (const candidate of candidates) {
    if (existsSync(path.join(candidate, "claude-code.toml"))) {
      return candidate;
    }
  }
  return null;
}

// Failure is never fatal — a missing sample or unwritable dir costs the menu
// entry, not startup.
export function installBundledRegistrations(): void {
  try {
    const registrationsDir = getRegistrationsDir();
    const sentinel = path.join(registrationsDir, SENTINEL_FILE_NAME);
    if (existsSync(sentinel)) {
      return;
    }
    const sourceDir = bundledClaudeCodeDir();
    if (sourceDir === null) {
      return;
    }
    mkdirSync(registrationsDir, { recursive: true });
    // Files are copied verbatim; the TOML's {terminal_agents_directory}
    // placeholder is resolved at command-render time, not rewritten here.
    for (const fileName of BUNDLED_FILE_NAMES) {
      const destination = path.join(registrationsDir, fileName);
      if (!existsSync(destination)) {
        copyFileSync(path.join(sourceDir, fileName), destination);
      }
    }
    writeFileSync(
      sentinel,
      "The bundled Claude Code registration was installed once into this directory.\n" +
        "This marker makes deleting claude-code.toml permanent — remove it to have\n" +
        "Sculptor re-install the registration on the next start.\n",
    );
  } catch {
    // Best-effort: a missing sample or unwritable dir must not break startup.
  }
}
