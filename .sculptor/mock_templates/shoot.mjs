// Renders mock states to PNGs, matching the app's retina rendering.
//
// Usage (from anywhere in the repo):
//   node .sculptor/mock_templates/shoot.mjs <mocks.html> <out-dir> <state> [state...]
//
// Each state renders <mocks.html>?state=<state>&bare=1 at 1440x900 @2x to
// <out-dir>/mock-<state>.png.
//
// Two rules when iterating with a user:
//   - Post the PNGs inline in chat as <img src="/abs/path"> tags.
//   - NEVER overwrite a PNG already posted to chat — earlier messages
//     reference the file on disk. Bump a version suffix instead (copy this
//     script next to your mock and edit, or rename outputs per round).
//
// playwright-core is resolved from the frontend's node_modules relative to
// THIS FILE, so a copy of this script must also sit two directories below
// the repo root (e.g. agent_docs/<slug>/shoot.mjs).
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const { chromium } = await import(
  new URL("../../sculptor/frontend/node_modules/playwright-core/index.mjs", import.meta.url).href
);

const [mockPath, outDir, ...states] = process.argv.slice(2);
if (!mockPath || !outDir || states.length === 0) {
  console.error("usage: node shoot.mjs <mocks.html> <out-dir> <state> [state...]");
  process.exit(1);
}

const mockUrl = pathToFileURL(resolve(mockPath)).href;
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await context.newPage();

for (const state of states) {
  await page.goto(`${mockUrl}?state=${state}&bare=1`, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(150);
  const out = resolve(outDir, `mock-${state}.png`);
  await page.screenshot({ path: out });
  console.log(`shot: ${out}`);
}

await browser.close();
