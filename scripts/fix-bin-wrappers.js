#!/usr/bin/env node
// Fix node_modules/.bin entries in environments where symlinks are not supported
// (e.g., Modal sandboxes). Replaces dereferenced copies with shell wrapper scripts
// that exec the real binary via node.
const fs = require("fs");
const path = require("path");

const cwd = process.cwd();
const binDir = path.join(cwd, "node_modules/.bin");
const pkgDir = path.join(cwd, "node_modules");

function findBins(dir) {
  const map = {};
  let entries;
  try {
    entries = fs.readdirSync(dir);
  } catch {
    return map;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry);
    if (entry.startsWith(".")) continue;
    if (entry.startsWith("@")) {
      try {
        Object.assign(map, findBins(full));
      } catch {
        // skip
      }
      continue;
    }
    try {
      const pkg = JSON.parse(
        fs.readFileSync(path.join(full, "package.json"), "utf8"),
      );
      if (typeof pkg.bin === "string") {
        map[pkg.name.split("/").pop()] = path.join(full, pkg.bin);
      } else if (typeof pkg.bin === "object") {
        for (const [k, v] of Object.entries(pkg.bin)) {
          map[k] = path.join(full, v);
        }
      }
    } catch {
      // skip packages without valid package.json or bin field
    }
  }
  return map;
}

const bins = findBins(pkgDir);
let fixed = 0;
for (const [name, target] of Object.entries(bins)) {
  const binPath = path.join(binDir, name);
  if (!fs.existsSync(binPath)) continue;
  const stat = fs.lstatSync(binPath);
  if (stat.isSymbolicLink()) continue; // already a symlink, no fix needed
  // Replace with wrapper that execs the real target
  const wrapper = `#!/bin/sh\nexec node ${JSON.stringify(target)} "$@"\n`;
  fs.writeFileSync(binPath, wrapper, { mode: 0o755 });
  fixed++;
}
console.log(`Fixed ${fixed} bin wrappers in ${binDir}`);
