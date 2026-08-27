// Renders each mock state to a PNG in the Sculptor workspace attachments directory
// (where chat-visible images live). Run from anywhere:  node agent_docs/layouts/shoot.mjs
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// Paths are derived from this script's own location so the shoot works in any
// checkout (no hardcoded home directory). The repo lives at <workspace>/code, and
// the attachments dir is its <workspace>/attachments sibling.
const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "../..");
const OUT = resolve(repoRoot, "../attachments");
const MOCK = pathToFileURL(join(scriptDir, "mocks.html")).href;

const { chromium } = await import(
  pathToFileURL(join(repoRoot, "sculptor/frontend/node_modules/playwright-core/index.mjs")).href
);

// PNGs already posted to chat are referenced by earlier messages — never
// overwrite them. Shoot only the states being iterated on, with a version
// suffix that bumps whenever a previously-posted state changes.
const VERSION = "-v12";
const STATES = ["tidy"];

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await context.newPage();

for (const state of STATES) {
  await page.goto(`${MOCK}?state=${state}&bare=1`, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(150);
  // The alert dialogs float centered over the overlay; a tight element crop reads
  // better for review than a full-viewport shot. Palette states screenshot the page.
  const alert = page.locator(".alert");
  if (await alert.count()) {
    await alert.screenshot({ path: `${OUT}/layouts-${state}${VERSION}.png` });
  } else {
    await page.screenshot({ path: `${OUT}/layouts-${state}${VERSION}.png` });
  }
  console.log(`shot: layouts-${state}${VERSION}.png`);
}

// Close-up crop of the sidebar bottom cluster (Layouts entry in context).
if (STATES.includes("sidebar")) {
  await page.goto(`${MOCK}?state=sidebar&bare=1`, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(150);
  await page.screenshot({ path: `${OUT}/layouts-sidebar-crop.png`, clip: { x: 0, y: 744, width: 264, height: 156 } });
  console.log("shot: layouts-sidebar-crop.png");
}

await browser.close();
