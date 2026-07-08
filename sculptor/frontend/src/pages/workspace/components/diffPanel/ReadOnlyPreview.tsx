import type { FileOptions, SupportedLanguages } from "@pierre/diffs";
import { File as PierreFile } from "@pierre/diffs/react";
import { Flex, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { MouseEvent as ReactMouseEvent, ReactElement } from "react";
import { useCallback, useLayoutEffect, useMemo, useRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";

import { ElementIds } from "~/api";
import { themeCodeThemeAtom } from "~/common/state/atoms/themeBuilder.ts";
import { appThemeAtom, fileBrowserLineWrappingAtom } from "~/common/state/atoms/userConfig.ts";
import { useWorkspaceFileContent } from "~/common/state/hooks/useWorkspaceFileContent.ts";
import { getShikiThemes } from "~/common/theme/shikiThemes.ts";
import { parseFrontmatter } from "~/components/MarkdownDiff/frontmatter.ts";
import { FrontmatterBlock } from "~/components/MarkdownDiff/FrontmatterBlock.tsx";
import { MarkdownAnchor } from "~/components/MarkdownDiff/MarkdownAnchor.tsx";
import {
  FILE_MARKDOWN_REHYPE_PLUGINS,
  FILE_MARKDOWN_REMARK_PLUGINS,
  safeUrlTransform,
} from "~/components/MarkdownDiff/markdownPlugins.ts";
import { VerticalOverlayScrollbar } from "~/components/VerticalOverlayScrollbar.tsx";

import type { MarkdownRenderMode } from "./atoms.ts";
import { isMarkdownPath, markdownRenderModeAtom, spotlightInsertAtom } from "./atoms.ts";
import pierreStyles from "./PierreDiffView.module.scss";
import {
  adoptPierreOverrideSheet,
  createPierreOverrideSheet,
  HIDE_NATIVE_HSCROLLBAR_CSS,
} from "./pierreShadowStyles.ts";
import styles from "./ReadOnlyPreview.module.scss";
import { StickyHorizontalScrollbar } from "./StickyHorizontalScrollbar.tsx";
import type { SpotlightData } from "./types.ts";
import { usePierreHighlighterReady } from "./usePierreHighlighterReady.ts";
import { useSpotlightCapture } from "./useSpotlightCapture.ts";

type ReadOnlyPreviewProps = {
  workspaceId: string;
  filePath: string;
  /** When set, wins over the persisted global render-mode preference — used by
   *  the quick-open-rendered-markdown path so one explicit open never rewrites
   *  the preference itself. */
  renderModeOverride?: MarkdownRenderMode;
  /** Enables spotlight capture on code files (skipped for rendered markdown). */
  spotlightScope?: SpotlightData["scope"];
};

// The shared Pierre background override plus the native-scrollbar hide (this
// preview replaces it with StickyHorizontalScrollbar at the panel bottom).
const bgOverrideSheet = createPierreOverrideSheet(HIDE_NATIVE_HSCROLLBAR_CSS);

const EXTENSION_LANGUAGE_MAP: Record<string, SupportedLanguages> = {
  ts: "typescript",
  tsx: "tsx",
  js: "javascript",
  jsx: "jsx",
  py: "python",
  rb: "ruby",
  rs: "rust",
  go: "go",
  java: "java",
  c: "c",
  cpp: "cpp",
  h: "c",
  hpp: "cpp",
  cs: "csharp",
  swift: "swift",
  kt: "kotlin",
  scala: "scala",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  xml: "xml",
  html: "html",
  css: "css",
  scss: "scss",
  less: "less",
  md: "markdown",
  sql: "sql",
  graphql: "graphql",
  dockerfile: "dockerfile",
  makefile: "makefile",
  lua: "lua",
  php: "php",
  r: "r",
  dart: "dart",
  vue: "vue",
  svelte: "svelte",
};

const getLanguageFromPath = (filePath: string): SupportedLanguages | undefined => {
  const ext = filePath.split(".").pop()?.toLowerCase();
  if (!ext) return undefined;
  return EXTENSION_LANGUAGE_MAP[ext];
};

// react-markdown hands its components map a renderer-internal `node` prop
// alongside the regular HTML attributes. We deliberately destructure only
// the documented props (no `...rest` spread) — otherwise React serialises
// `node` as `node="[object Object]"` in the DOM. `MarkdownAnchor` itself
// holds the link-routing contract (target=_blank for external, click
// preventDefault for fragment / relative).
const READ_ONLY_PREVIEW_COMPONENTS: Components = {
  a: ({ children, href, title }) => (
    <MarkdownAnchor href={href} title={title}>
      {children}
    </MarkdownAnchor>
  ),
};

export const ReadOnlyPreview = ({
  workspaceId,
  filePath,
  renderModeOverride,
  spotlightScope = "file-view",
}: ReadOnlyPreviewProps): ReactElement => {
  const { data: content, isPending, isError: hasError } = useWorkspaceFileContent(workspaceId, filePath, null);
  const overflow = useAtomValue(fileBrowserLineWrappingAtom);
  const appTheme = useAtomValue(appThemeAtom);
  const codeTheme = useAtomValue(themeCodeThemeAtom);
  const shikiThemes = getShikiThemes(codeTheme);
  // Pierre must not MOUNT before its shared highlighter has these themes
  // attached — a cold-themes first mount paints nothing and does not survive
  // React StrictMode's remount (see usePierreHighlighterReady).
  const isHighlighterReady = usePierreHighlighterReady(shikiThemes);
  const globalMarkdownMode = useAtomValue(markdownRenderModeAtom);
  const markdownMode = renderModeOverride ?? globalMarkdownMode;
  const pierreRef = useRef<HTMLDivElement>(null);
  // The scroll container (native scrollbar suppressed in CSS); VerticalOverlayScrollbar
  // draws a persistent vertical bar off it, since a styled native scrollbar renders
  // nothing at rest under macOS overlay-scrollbar mode.
  const containerRef = useRef<HTMLDivElement>(null);
  const shouldRenderMarkdown = isMarkdownPath(filePath) && markdownMode === "rendered";

  // Inject our override stylesheet into Pierre's shadow DOM (see
  // adoptPierreOverrideSheet for why this is a layout effect). The container
  // only exists once content has loaded AND the highlighter gate has opened
  // (Pierre mounts at that point). Re-run on overflow changes because Pierre
  // re-creates its shadow DOM when the wrap mode flips, and when
  // `isHighlighterReady` flips (though it isn't read here) so the sheet is
  // adopted the moment Pierre first mounts.
  const hasContent = content != null;
  useLayoutEffect(() => {
    if (!hasContent) return;
    adoptPierreOverrideSheet(pierreRef.current, bgOverrideSheet);
  }, [hasContent, overflow, isHighlighterReady]);

  const fileName = useMemo(() => filePath.split("/").pop() ?? filePath, [filePath]);
  const lang = useMemo(() => getLanguageFromPath(filePath), [filePath]);

  const fileOptions = useMemo(
    (): FileOptions<undefined> => ({
      overflow,
      themeType: appTheme,
      theme: shikiThemes,
      disableFileHeader: true,
    }),
    [overflow, appTheme, shikiThemes],
  );

  const fileContents = useMemo(() => {
    if (content == null) return null;
    return { name: fileName, contents: content, lang };
  }, [content, fileName, lang]);

  // Split frontmatter off the body only when the markdown is actually being
  // rendered, and memoize it so unrelated re-renders (theme, panel resize,
  // atom updates) don't reparse a potentially large file every time.
  const parsedMarkdown = useMemo(
    () => (shouldRenderMarkdown && content != null ? parseFrontmatter(content) : null),
    [shouldRenderMarkdown, content],
  );

  // --- Spotlight capture (code-view branch only) --------------------------
  const setSpotlight = useSetAtom(spotlightInsertAtom);
  const spotlight = useSpotlightCapture({
    containerRef: pierreRef,
    isHighlighterReady,
  });

  const handleSpotlightCommit = useCallback((): void => {
    const lineStart = spotlight.dragEndLine ?? spotlight.dragStartLine ?? spotlight.hoveredLine?.line;
    const lineEnd = spotlight.dragEndLine ?? spotlight.dragStartLine ?? spotlight.hoveredLine?.line;
    if (lineStart === null || lineStart === undefined || lineEnd === null || lineEnd === undefined) return;
    const start = Math.min(lineStart, lineEnd);
    const end = Math.max(lineStart, lineEnd);
    const capture = spotlight.resolveCapture(filePath, start, end);
    if (!capture) return;
    setSpotlight({
      file: filePath,
      lineStart: start,
      lineEnd: end,
      side: null,
      snippet: capture.snippet,
      snippetCapturedAt: new Date().toISOString(),
      scope: spotlightScope,
    });
  }, [spotlight, filePath, spotlightScope, setSpotlight]);

  const handleSpotlightButtonMouseDown = useCallback(
    (e: ReactMouseEvent): void => {
      spotlight.onButtonMouseDown(e);
    },
    [spotlight],
  );

  const handleSpotlightButtonMouseUp = useCallback(
    (e: ReactMouseEvent): void => {
      spotlight.onButtonMouseUp(e);
      if (!spotlight.isDragging) {
        handleSpotlightCommit();
      }
    },
    [spotlight, handleSpotlightCommit],
  );

  const activeLine = spotlight.hoveredLine?.line ?? null;
  const activeRect = spotlight.hoveredLine?.rect;
  const isSpotlightButtonVisible = activeLine !== null && activeRect && isHighlighterReady;
  // --- end Spotlight capture ----------------------------------------------

  if (isPending) {
    return (
      <Flex align="center" justify="center" flexGrow="1">
        <Text size="2" color="gray">
          Loading file...
        </Text>
      </Flex>
    );
  }

  if (hasError || fileContents == null) {
    return (
      <Flex align="center" justify="center" flexGrow="1">
        <Text size="2" color="gray">
          Could not load file content
        </Text>
      </Flex>
    );
  }

  if (shouldRenderMarkdown && parsedMarkdown != null) {
    // Frontmatter is stripped before `react-markdown` sees the content —
    // otherwise the closing `---` underlines the `key: value` lines into a
    // setext `<h2>`. It's rendered as a styled metadata block instead; the
    // source view (eye-toggle off, below) keeps showing it verbatim.
    const { frontmatter, body } = parsedMarkdown;
    // Plugin policy lives in `markdownPlugins.ts`. `data-markdown-body`
    // scopes the fragment-anchor scroll lookup in `anchorBehavior.ts` so
    // a `#install` click never lands on an unrelated id elsewhere in the
    // app shell.
    return (
      <div className={styles.wrapper} data-testid={ElementIds.READ_ONLY_PREVIEW}>
        {/* A plain <div>, not a Radix <Box>: the code branch's scroll container
            is also a <div>, so switching between a code file and a markdown one
            reuses the same DOM node instead of swapping element types — which
            would strand VerticalOverlayScrollbar observing the detached old
            node (its effect only re-reads on remount). Padding lives in
            `.markdownBody` instead of a `p` prop for the same reason. */}
        <div
          ref={containerRef}
          className={`${styles.container} ${styles.markdownBody}`}
          data-testid={ElementIds.READ_ONLY_PREVIEW_MARKDOWN}
          data-markdown-body
        >
          {/* Single content wrapper so it's always the scroll container's
              firstElementChild — the element VerticalOverlayScrollbar observes
              for content growth. Rendering the frontmatter and body as separate
              direct children would leave later growth (e.g. a late image load)
              unobserved and the thumb stale. */}
          <div>
            {frontmatter && <FrontmatterBlock frontmatter={frontmatter} />}
            <ReactMarkdown
              remarkPlugins={FILE_MARKDOWN_REMARK_PLUGINS}
              rehypePlugins={FILE_MARKDOWN_REHYPE_PLUGINS}
              urlTransform={safeUrlTransform}
              components={READ_ONLY_PREVIEW_COMPONENTS}
            >
              {body}
            </ReactMarkdown>
          </div>
        </div>
        <VerticalOverlayScrollbar scrollRef={containerRef} thumbTestId={ElementIds.READ_ONLY_PREVIEW_SCROLLBAR_THUMB} />
      </div>
    );
  }

  // Only the Pierre source view below needs the highlighter; the markdown
  // branch above renders without it. The gate resolves in milliseconds, so it
  // shares the file fetch's loading placeholder rather than a distinct state.
  if (!isHighlighterReady) {
    return (
      <Flex align="center" justify="center" flexGrow="1">
        <Text size="2" color="gray">
          Loading file...
        </Text>
      </Flex>
    );
  }

  return (
    <div className={styles.wrapper} data-testid={ElementIds.READ_ONLY_PREVIEW}>
      <div ref={containerRef} className={styles.container}>
        {isSpotlightButtonVisible && (
          <button
            type="button"
            data-testid={ElementIds.SPOTLIGHT_LINE_HOVER_BUTTON}
            className={pierreStyles.spotlightButton}
            style={{
              position: "fixed",
              left: `${activeRect.left - 28}px`,
              top: `${activeRect.top + activeRect.height / 2 - 10}px`,
              opacity: spotlight.isDragging ? 1 : undefined,
            }}
            onMouseDown={handleSpotlightButtonMouseDown}
            onMouseUp={handleSpotlightButtonMouseUp}
          >
            +
          </button>
        )}
        <div ref={pierreRef}>
          <PierreFile file={fileContents} options={fileOptions} />
        </div>
      </div>
      <VerticalOverlayScrollbar scrollRef={containerRef} thumbTestId={ElementIds.READ_ONLY_PREVIEW_SCROLLBAR_THUMB} />
      {overflow === "scroll" && <StickyHorizontalScrollbar containerRef={pierreRef} />}
    </div>
  );
};
