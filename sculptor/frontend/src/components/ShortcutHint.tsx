import type { ReactElement } from "react";

import { formatShortcutForDisplay } from "~/common/ShortcutUtils.ts";

/**
 * Render a keybinding hint as a single <kbd> with the platform-formatted
 * display string. We deliberately do NOT split into per-character <kbd>s: the
 * Mac modifier glyphs (⌘ ⇧ ⌥ ⌃) only render legibly when the system font lays
 * them out as a single text run with kerning / ligature lookups in play —
 * splitting per-character makes thin glyphs like ⇧ look like a ghost.
 *
 * `binding` is the raw keybinding (e.g. "Meta+Enter"); this component owns the
 * display formatting. Callers pass their own className to control placement and
 * spacing.
 */
export const ShortcutHint = ({ binding, className }: { binding: string; className?: string }): ReactElement => {
  const display = formatShortcutForDisplay(binding);
  if (!display) {
    return <></>;
  }
  return (
    <kbd className={className} aria-label={`Shortcut: ${display}`}>
      {display}
    </kbd>
  );
};
