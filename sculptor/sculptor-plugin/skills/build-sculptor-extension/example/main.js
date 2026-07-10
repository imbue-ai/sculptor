// Hand-written ESM, imported directly by the host (no bundler). The skill's
// quick start loads this exact directory, and Sculptor's e2e tests load it too,
// so it doubles as the canonical smallest-possible extension.
export default function activate(api) {
  const el = document.createElement("div");
  el.textContent = "hello from an extension";
  el.style.cssText = "position:fixed;bottom:16px;right:16px;pointer-events:auto;";
  document.body.appendChild(el);
  return () => el.remove(); // disposer — REQUIRED cleanup on unload/reload
}
