/**
 * Extract plain text content from an HTML string, stripping all tags and attributes.
 *
 * TipTap serializes Mention nodes as HTML `<span>` elements. This helper converts
 * such strings to the visible text the user would expect when copying a message.
 */
export const stripHtml = (html: string): string => {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return doc.body.textContent ?? "";
};
