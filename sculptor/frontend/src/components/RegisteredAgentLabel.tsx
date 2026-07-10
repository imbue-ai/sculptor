import type { ReactElement } from "react";

import styles from "./RegisteredAgentLabel.module.scss";

/**
 * Render a registered terminal agent's label: its user-set display name plus a
 * muted "terminal" tag marking it as coming from the user's terminal-based
 * configuration rather than a built-in harness (Claude / pi / Terminal). The
 * registration's display name is user-controlled and carries no origin marker,
 * so every picker that lists registered agents beside the built-ins renders
 * through this one component — keeping the marker identical across the tab-bar
 * `+` sub-menu, the new-workspace picker, and the CI babysitter select.
 *
 * The tag is a plain <span> so it inherits the surrounding font size (these
 * pickers render at different sizes — the size-1 new-workspace trigger vs. the
 * default-size menus) and carries the add-panel menu's --gray-10 secondary-text
 * color via one class. A literal space (not just the span's CSS gap) separates
 * it from the name, so the option's accessible name and Radix Select typeahead
 * read "<name> terminal" rather than running the two words together.
 */
export const RegisteredAgentLabel = ({ displayName }: { displayName: string }): ReactElement => (
  <>
    {displayName} <span className={styles.terminalTag}>terminal</span>
  </>
);
