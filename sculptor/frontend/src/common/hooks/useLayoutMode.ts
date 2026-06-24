// The desktop/mobile seam (component_hierarchy.md → "Mobile shell variant"). The
// page-level shell branches on a single hook so the mobile shell can land later
// without threading a flag through the tree. For now this is a real seam but a
// no-op: it always reports desktop and never builds the mobile shell.

export type LayoutMode = "desktop" | "mobile";

// Always desktop for now. The mobile breakpoint detection lands with
// MobileWorkspaceShell; until then every caller takes the desktop branch.
export const useLayoutMode = (): LayoutMode => {
  return "desktop";
};

export const useIsMobile = (): boolean => {
  return useLayoutMode() === "mobile";
};
