import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import type { ParsedFrontmatter } from "./frontmatter.ts";
import styles from "./FrontmatterBlock.module.scss";

const isScalar = (value: unknown): boolean =>
  value == null || typeof value === "string" || typeof value === "number" || typeof value === "boolean";

// Collapse runs of whitespace (including the newlines a YAML block scalar
// preserves, e.g. `description: |`) into single spaces so a multi-line value
// reads — and copies — as one flowing paragraph in the compact table cell.
// The verbatim text is still available via the source view.
const collapseWhitespace = (value: string): string => value.replace(/\s+/g, " ").trim();

/**
 * Render a frontmatter value as a single readable string. Scalars print as-is;
 * arrays of scalars join with commas (the common `tags: [a, b]` case);
 * anything deeper falls back to compact JSON so nested structure is visible
 * but never explodes the layout.
 */
const formatValue = (value: unknown): string => {
  if (value == null) return "";
  if (typeof value === "string") return collapseWhitespace(value);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value) && value.every(isScalar)) {
    return value.map((item) => (item == null ? "" : String(item))).join(", ");
  }
  return JSON.stringify(value);
};

type FrontmatterBlockProps = {
  frontmatter: ParsedFrontmatter;
};

/**
 * Styled metadata table rendered above the markdown body for a `.md` file that
 * opens with YAML/TOML frontmatter. Parsed mappings render as a bordered
 * key/value table; anything we can't parse into rows (TOML, or malformed YAML)
 * falls back to the verbatim source so no content is silently dropped.
 */
export const FrontmatterBlock = ({ frontmatter }: FrontmatterBlockProps): ReactElement => {
  const { data, raw, lang } = frontmatter;
  const entries = data ? Object.entries(data) : [];

  return (
    <div className={styles.block} data-testid={ElementIds.READ_ONLY_PREVIEW_FRONTMATTER} data-frontmatter-lang={lang}>
      {data && entries.length > 0 ? (
        <table className={styles.table}>
          <tbody>
            {entries.map(([key, value]) => (
              <tr key={key}>
                <th scope="row" className={styles.key}>
                  {key}
                </th>
                <td className={styles.value}>{formatValue(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <pre className={styles.raw}>{raw}</pre>
      )}
    </div>
  );
};
