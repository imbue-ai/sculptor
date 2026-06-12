const host = window.__SCULPTOR_HOST__;
if (!host || !host.radixThemes) {
  throw new Error(
    "Sculptor plugin runtime: window.__SCULPTOR_HOST__.radixThemes missing.",
  );
}
const RT = host.radixThemes;

// Named exports cover the surface plugins are expected to use. Add more here
// (and to hostRuntime.ts) as the SDK grows.
export const Theme = RT.Theme;
export const Flex = RT.Flex;
export const Grid = RT.Grid;
export const Box = RT.Box;
export const Container = RT.Container;
export const Section = RT.Section;
export const Text = RT.Text;
export const Heading = RT.Heading;
export const Link = RT.Link;
export const Button = RT.Button;
export const IconButton = RT.IconButton;
export const Badge = RT.Badge;
export const Card = RT.Card;
export const Separator = RT.Separator;
export const Spinner = RT.Spinner;
export const Skeleton = RT.Skeleton;
export const Tooltip = RT.Tooltip;
export const Popover = RT.Popover;
export const Dialog = RT.Dialog;
export const DropdownMenu = RT.DropdownMenu;
export const ContextMenu = RT.ContextMenu;
export const TextField = RT.TextField;
export const TextArea = RT.TextArea;
export const Checkbox = RT.Checkbox;
export const Switch = RT.Switch;
export const Select = RT.Select;
export const Tabs = RT.Tabs;
export const ScrollArea = RT.ScrollArea;
