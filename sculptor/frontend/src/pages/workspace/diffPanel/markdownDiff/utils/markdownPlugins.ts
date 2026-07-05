import { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { PluggableList } from "unified";

// Single source of truth for how *file* content is rendered as markdown.
// File content is less trusted than chat output, so this layer is
// intentionally narrow:
//
//  1. `remark-gfm` is the only remark plugin — enables tables,
//     strikethrough, task lists, and autolinks. GFM emit shapes are plain
//     semantic HTML (`<table>`, `<input type="checkbox" disabled>`, `<del>`,
//     `<a>`) with no inline scripts or attribute injection vectors.
//  2. No rehype plugins. In particular, no `rehype-raw` — raw HTML in the
//     source markdown is rendered as text (react-markdown's default), so a
//     `<script>` tag in a `.md` file is inert.
//  3. `safeUrlTransform` blocks `javascript:`, `data:`, `vbscript:`, and
//     other unknown protocols on every URL attribute. It is wired
//     explicitly even though it matches the react-markdown default — the
//     same primitive is used by the shared `MarkdownAnchor` component for
//     defense-in-depth.

export const FILE_MARKDOWN_REMARK_PLUGINS: PluggableList = [remarkGfm];
export const FILE_MARKDOWN_REHYPE_PLUGINS: PluggableList = [];

// Re-exported under an explicit name so consumers that don't go through
// react-markdown's built-in `urlTransform` (future diff renderer, the
// shared `MarkdownAnchor` component) can call the same primitive on
// `<a href>` and `<img src>` themselves. The `MarkdownAnchor` component
// runs this on every href it receives — that's the actual filter; the
// `urlTransform` prop on `<ReactMarkdown>` is a redundant outer layer.
export const safeUrlTransform: (url: string) => string = defaultUrlTransform;
