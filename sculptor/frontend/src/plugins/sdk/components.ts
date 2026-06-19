/**
 * Sculptor first-party components plugins can use. The generated SDK runtime
 * stub (served at `/plugin-runtime/sculptor-plugin-sdk.js`) re-exports these
 * from the `window.__SCULPTOR_HOST__.sdk` object the host populates at boot.
 */
export { PanelHeader } from "~/components/panels/PanelHeader.tsx";

// The host's general-purpose markdown renderer, exposed under a stable SDK
// name. Takes `{ content: string }` and renders GFM (links open in a new tab,
// code blocks get copy buttons) — so plugins can show rich text from external
// systems without bundling their own markdown stack.
export { MarkdownBlock as Markdown } from "~/components/MarkdownBlock.tsx";
