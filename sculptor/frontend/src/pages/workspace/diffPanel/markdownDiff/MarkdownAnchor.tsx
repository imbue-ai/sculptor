import { ExternalLink, Link2Off } from "lucide-react";
import type { ReactElement, ReactNode } from "react";

import styles from "./MarkdownAnchor.module.scss";
import { handleInternalMarkdownAnchorClick, hasExternalProtocol } from "./utils/anchorBehavior.ts";
import { safeUrlTransform } from "./utils/markdownPlugins.ts";

// Single anchor renderer shared by `ReadOnlyPreview` (react-markdown
// components map) and the future `MarkdownDiff` (hast-util-to-jsx-runtime
// components map). The component's only DOM-bound props are `href`,
// `title`, and `children` plus the routing attributes the component sets
// itself.
//
// That tight prop list is intentional. Both react-markdown and
// hast-util-to-jsx-runtime hand component overrides a renderer-internal
// `node` prop (the hast Element) alongside the regular HTML attributes;
// spreading the whole prop bag onto the `<a>` makes React serialise it
// as `node="[object Object]"` in the DOM. Callers in the consumer
// components destructure the three real props and hand them in here.
//
// Every rendered anchor gets a `data-link-kind` attribute so CSS (both
// the colocated module and consumer stylesheets) can differentiate the
// three link kinds without re-running the protocol check:
//
//   external — URL has a scheme; opens in OS browser via target="_blank";
//              suffixed with a lucide `ExternalLink` icon
//   fragment — `#anchor` link; preventDefault on click, would scroll to a
//              matching id but heading-id generation isn't wired yet
//              (tracked in SCU-767); rendered with a dashed underline +
//              tooltip explaining the limitation
//   relative — schemaless or `./foo` / `/foo`; preventDefault on click,
//              file-link navigation isn't wired yet; suffixed with a
//              lucide `Link2Off` (broken-chain) icon + tooltip
type MarkdownAnchorProps = {
  href?: string | null | undefined;
  title?: string | null | undefined;
  children?: ReactNode;
};

const ICON_SIZE = 14;

// Default tooltips for the unsupported kinds — a caller-provided `title`
// (e.g. from markdown's `[text](href "title")` syntax) wins.
const FRAGMENT_NOT_SUPPORTED_TITLE = "In-page anchor links aren't supported yet";
const RELATIVE_NOT_SUPPORTED_TITLE = "Linked-file navigation isn't supported yet";

export const MarkdownAnchor = ({ href, title, children }: MarkdownAnchorProps): ReactElement => {
  // `safeUrlTransform` is run here, not just at the react-markdown
  // boundary, because the future `MarkdownDiff` consumer goes through
  // `hast-util-to-jsx-runtime` which does NOT apply react-markdown's
  // urlTransform. Without this call `hasExternalProtocol` would
  // green-light `javascript:` / `data:` / `vbscript:` URLs (its regex
  // matches any RFC 3986 scheme — the *filtering* is what
  // `safeUrlTransform` does, returning "" for everything outside the
  // allow-list). For the `ReadOnlyPreview` path this is belt-and-suspenders
  // (react-markdown already filtered upstream); for the diff path it is
  // the only line of defense.
  const rawHref = typeof href === "string" ? href : "";
  const safeHref = safeUrlTransform(rawHref);
  if (hasExternalProtocol(safeHref)) {
    return (
      <a data-link-kind="external" href={safeHref} title={title ?? undefined} target="_blank" rel="noopener noreferrer">
        {children}
        <ExternalLink size={ICON_SIZE} aria-hidden className={styles.icon} />
      </a>
    );
  }

  if (safeHref.startsWith("#")) {
    return (
      <a
        className={styles.dashedUnderline}
        data-link-kind="fragment"
        href={safeHref}
        title={title ?? FRAGMENT_NOT_SUPPORTED_TITLE}
        onClick={handleInternalMarkdownAnchorClick}
      >
        {children}
      </a>
    );
  }
  // Relative paths, schemaless hrefs, and anything `safeUrlTransform`
  // stripped (e.g. `javascript:` -> "") all fall here.
  return (
    <a
      data-link-kind="relative"
      href={safeHref || undefined}
      title={title ?? RELATIVE_NOT_SUPPORTED_TITLE}
      onClick={handleInternalMarkdownAnchorClick}
    >
      {children}
      <Link2Off size={ICON_SIZE} aria-hidden className={styles.icon} />
    </a>
  );
};
