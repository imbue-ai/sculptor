import type { BundledLanguage, BundledTheme, HighlighterGeneric, ThemedToken } from "shiki/bundle/web";
import { createHighlighter } from "shiki/bundle/web";

/** A token with colors for both light and dark themes. */
export type DualThemedToken = {
  content: string;
  lightColor: string | undefined;
  darkColor: string | undefined;
};

/**
 * Lazy singleton shiki highlighter.
 *
 * Uses the `shiki/bundle/web` entry which bundles common web languages and
 * loads grammars and themes on demand.
 */
let highlighterPromise: Promise<HighlighterGeneric<BundledLanguage, BundledTheme>> | null = null;

const getHighlighter = (): Promise<HighlighterGeneric<BundledLanguage, BundledTheme>> => {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: [],
      langs: [],
    });
  }
  return highlighterPromise;
};

/**
 * Tokenize `code` with syntax highlighting for the given `language` and theme pair.
 *
 * Returns an array of lines, each containing tokens with both light and dark
 * colors. Returns `null` if the language is not supported.
 */
export const highlightCode = async (
  code: string,
  language: string,
  themes: { light: string; dark: string },
): Promise<ReadonlyArray<ReadonlyArray<DualThemedToken>> | null> => {
  const highlighter = await getHighlighter();

  // Load language if needed
  const loadedLangs = highlighter.getLoadedLanguages();
  if (!loadedLangs.includes(language)) {
    try {
      await highlighter.loadLanguage(language as BundledLanguage);
    } catch {
      return null;
    }
  }

  // Load themes if needed
  const loadedThemes = highlighter.getLoadedThemes();
  const themesToLoad = [themes.light, themes.dark].filter((t) => !loadedThemes.includes(t));
  if (themesToLoad.length > 0) {
    await Promise.all(themesToLoad.map((t) => highlighter.loadTheme(t as BundledTheme)));
  }

  const { tokens } = highlighter.codeToTokens(code, {
    lang: language as BundledLanguage,
    themes: {
      light: themes.light as BundledTheme,
      dark: themes.dark as BundledTheme,
    },
  });

  return tokens.map((line: ReadonlyArray<ThemedToken>) =>
    line.map(
      (token): DualThemedToken => ({
        content: token.content,
        lightColor: token.htmlStyle?.["color"],
        darkColor: token.htmlStyle?.["--shiki-dark"],
      }),
    ),
  );
};
