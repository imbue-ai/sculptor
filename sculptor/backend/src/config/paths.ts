import { existsSync } from "node:fs";
import path from "node:path";

// Resolves the directory holding the built frontend SPA. The Python backend
// serves sculptor/frontend-dist (falling back to sculptor/frontend/dist). We
// support both dev layouts and a packaged layout via the SCULPTOR_STATIC_DIR
// override (set by the launcher/packaging in Task 9.1). Returns the first
// candidate that actually contains an index.html, or undefined when no built
// frontend is present (e.g. unit tests, OpenAPI emit) so static serving is
// simply skipped.
export function resolveStaticAssetDir(
  env: NodeJS.ProcessEnv = process.env,
  cwd: string = process.cwd(),
): string | undefined {
  const candidates: string[] = [];
  if (env.SCULPTOR_STATIC_DIR !== undefined && env.SCULPTOR_STATIC_DIR !== "") {
    candidates.push(env.SCULPTOR_STATIC_DIR);
  }
  candidates.push(
    path.resolve(cwd, "sculptor/frontend-dist"),
    path.resolve(cwd, "sculptor/frontend/dist"),
    path.resolve(cwd, "frontend-dist"),
    path.resolve(cwd, "frontend/dist"),
    path.resolve(cwd, "../frontend-dist"),
    path.resolve(cwd, "../frontend/dist"),
  );
  for (const dir of candidates) {
    if (existsSync(path.join(dir, "index.html"))) {
      return dir;
    }
  }
  return undefined;
}
