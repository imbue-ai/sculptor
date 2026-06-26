import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

// Bundled-plugin discovery (common/plugin.py). Sculptor ships its slash-command
// plugins (sculptor-plugin / sculptor-workflow / sculptor-experimental) as
// directories alongside the backend; the skills endpoint namespaces their skills
// and the claude harness loads them with --plugin-dir.

const PLUGIN_NAMES = [
  "sculptor-plugin",
  "sculptor-workflow",
  "sculptor-experimental",
];

// The directory containing the bundled plugin directories. From source the
// backend bundle lives at <repo>/sculptor/backend/dist, so the plugins are two
// levels up at <repo>/sculptor/. SCULPT_PLUGINS_DIR overrides this (the packaged
// app sets it, mirroring Python's export for terminal agents).
export function getPluginsBaseDir(
  env: NodeJS.ProcessEnv = process.env,
): string {
  const override = env.SCULPT_PLUGINS_DIR;
  if (override !== undefined && override !== "") {
    return override;
  }
  return path.resolve(__dirname, "..", "..");
}

// The bundled plugin directories that exist on disk, in load order.
export function getPluginDirs(env: NodeJS.ProcessEnv = process.env): string[] {
  const base = getPluginsBaseDir(env);
  return PLUGIN_NAMES.map((name) => path.join(base, name)).filter(
    (dir) => existsSync(dir) && statSync(dir).isDirectory(),
  );
}

// The plugin's namespace from .claude-plugin/plugin.json (name field), falling
// back to the directory name (skills.py _get_plugin_namespace).
export function getPluginNamespace(pluginDir: string): string {
  const pluginJson = path.join(pluginDir, ".claude-plugin", "plugin.json");
  try {
    const data = JSON.parse(readFileSync(pluginJson, "utf8")) as {
      name?: unknown;
    };
    if (typeof data.name === "string" && data.name) {
      return data.name;
    }
  } catch {
    // Missing or malformed — fall back to the dir name.
  }
  return path.basename(pluginDir);
}
