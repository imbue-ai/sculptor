/**
 * Check whether any dismissible overlay (dialog, menu, popover, select, or
 * suggestion list) is currently open. Used to prevent global keyboard handlers
 * from consuming events that should be handled by the topmost overlay.
 *
 * This relies on DOM attributes set by Radix UI, so new Radix-based overlays
 * are detected automatically without code changes here.
 *
 * `ignoreDialog` excludes one dialog element (and its descendants/ancestors)
 * from the dialog check. An overlay that hosts its own keyboard handler — e.g.
 * the new-workspace modal, whose form owns Cmd+Enter — passes its host dialog so
 * it doesn't treat ITSELF as a blocking overlay, while still bailing for any
 * other overlay stacked above it (a nested dialog, an open Select, a suggestion
 * list). Popper-based and TipTap overlays portal to the body, so they are
 * detected regardless of the ignored dialog.
 */
export const isDismissibleOverlayOpen = (ignoreDialog?: Element | null): boolean => {
  // Radix Dialog / AlertDialog (fixed-position overlays, not popper-based).
  const dialogs = document.querySelectorAll(
    '[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]',
  );
  for (const dialog of dialogs) {
    if (ignoreDialog && (dialog === ignoreDialog || dialog.contains(ignoreDialog) || ignoreDialog.contains(dialog))) {
      continue;
    }
    return true;
  }

  // Radix popper-based overlays (DropdownMenu, ContextMenu, Popover, Select).
  // These are conditionally mounted — the wrapper only exists while open.
  // Check the content child's role to exclude tooltips and hover cards.
  const popperWrappers = document.querySelectorAll("[data-radix-popper-content-wrapper]");
  for (const wrapper of popperWrappers) {
    const content = wrapper.firstElementChild;
    if (content) {
      const role = content.getAttribute("role");
      if (role === "menu" || role === "listbox" || role === "dialog") {
        return true;
      }
    }
  }

  // TipTap suggestion popovers (@-mention / /-skill lists). These are rendered
  // as position:absolute children of the root theme element via ReactRenderer,
  // outside the Radix component tree.
  //
  // Exclude Radix visually-hidden elements (e.g. accessible dialog titles) which
  // are always-present 1×1px spans with clip/overflow hidden — they are not
  // interactive overlays.
  const rootTheme = document.querySelector("[data-is-root-theme]");
  if (rootTheme) {
    for (const child of rootTheme.children) {
      if (child instanceof HTMLElement && child.style.position === "absolute") {
        if (child.style.overflow === "hidden" && child.style.width === "1px") {
          continue;
        }
        return true;
      }
    }
  }

  return false;
};
