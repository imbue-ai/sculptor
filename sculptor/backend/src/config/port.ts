// Resolves the listen host/port for the backend, matching the Python CLI:
// an explicit `--port` flag wins, then the SCULPTOR_API_PORT env var, then the
// default 5050 (see sculptor/sculptor/config/settings.py).
export const DEFAULT_BACKEND_PORT = 5050;

export function resolvePort(argv: readonly string[] = process.argv, env: NodeJS.ProcessEnv = process.env): number {
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === undefined) {
      continue;
    }
    if (arg.startsWith("--port=")) {
      const parsed = Number.parseInt(arg.slice("--port=".length), 10);
      if (Number.isInteger(parsed)) {
        return parsed;
      }
    } else if (arg === "--port" && i + 1 < argv.length) {
      const parsed = Number.parseInt(argv[i + 1] ?? "", 10);
      if (Number.isInteger(parsed)) {
        return parsed;
      }
    }
  }
  const fromEnv = env.SCULPTOR_API_PORT;
  if (fromEnv !== undefined && fromEnv !== "") {
    const parsed = Number.parseInt(fromEnv, 10);
    if (Number.isInteger(parsed)) {
      return parsed;
    }
  }
  return DEFAULT_BACKEND_PORT;
}

export function resolveBindHost(env: NodeJS.ProcessEnv = process.env): string {
  return env.SCULPTOR_BIND_HOST ?? "127.0.0.1";
}
