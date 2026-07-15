import { ContextMenu, DropdownMenu } from "@radix-ui/themes";
import { useAtomValue, useStore } from "jotai";
import { Copy, FolderOpenIcon, GitBranch, Stethoscope } from "lucide-react";
import type { ComponentType, ReactElement, ReactNode } from "react";
import { Fragment } from "react";

import { ElementIds, type ExternalApp, type Workspace } from "../../../api";
import { getOpenWithItems } from "../../../common/openInApp/items.tsx";
import type { AccentColor } from "../../../common/state/atoms/themeBuilder";
import { isWorkspaceGroupsEnabledAtom } from "../../../common/state/atoms/userConfig.ts";
import { useWorkspaceBranch } from "../../../common/state/hooks/useWorkspaceBranch.ts";
import { pendingWorkspaceRenameIdAtom, renamingWorkspaceIdAtom } from "./atoms.ts";
import type { WorkspaceAction } from "./types.ts";
import { WorkspaceGroupingMenuItems } from "./WorkspaceGroupingMenuItems.tsx";

/** Pixel size shared by every icon rendered in these context menus. */
export const ICON_SIZE = 14;

/**
 * The Radix menu primitives the workspace menu body renders through.
 * `ContextMenu.*` and `DropdownMenu.*` expose the same sub-API with
 * compatible props, so the same body can render into either the
 * right-click context menu or the sidebar row's "..." dropdown — keeping
 * the two menus in lockstep instead of maintaining two divergent lists.
 */
export type WorkspaceMenuComponents = {
  Item: ComponentType<{
    "data-group-id"?: string;
    "data-testid"?: string;
    color?: AccentColor;
    disabled?: boolean;
    onSelect?: (event: Event) => void;
    children?: ReactNode;
  }>;
  Separator: ComponentType;
  Label: ComponentType<{ children?: ReactNode }>;
  Sub: ComponentType<{ children?: ReactNode }>;
  SubTrigger: ComponentType<{ "data-testid"?: string; children?: ReactNode }>;
  SubContent: ComponentType<{ children?: ReactNode }>;
};

const CONTEXT_MENU_COMPONENTS: WorkspaceMenuComponents = {
  Item: ContextMenu.Item as WorkspaceMenuComponents["Item"],
  Separator: ContextMenu.Separator as WorkspaceMenuComponents["Separator"],
  Label: ContextMenu.Label as WorkspaceMenuComponents["Label"],
  Sub: ContextMenu.Sub as WorkspaceMenuComponents["Sub"],
  SubTrigger: ContextMenu.SubTrigger as WorkspaceMenuComponents["SubTrigger"],
  SubContent: ContextMenu.SubContent as WorkspaceMenuComponents["SubContent"],
};

const DROPDOWN_MENU_COMPONENTS: WorkspaceMenuComponents = {
  Item: DropdownMenu.Item as WorkspaceMenuComponents["Item"],
  Separator: DropdownMenu.Separator as WorkspaceMenuComponents["Separator"],
  Label: DropdownMenu.Label as WorkspaceMenuComponents["Label"],
  Sub: DropdownMenu.Sub as WorkspaceMenuComponents["Sub"],
  SubTrigger: DropdownMenu.SubTrigger as WorkspaceMenuComponents["SubTrigger"],
  SubContent: DropdownMenu.SubContent as WorkspaceMenuComponents["SubContent"],
};

type RenderMenuProps = {
  actions: ReadonlyArray<WorkspaceAction>;
  target: Workspace;
  /**
   * Radix accent color for destructive actions. Workspace tabs derive
   * this from the active theme builder; agent tabs use the literal "red".
   */
  destructiveColor: AccentColor;
  /**
   * Optional content to splice into the rendered menu immediately after
   * the action with the given id. Used by `WorkspaceContextMenuContent`
   * to inject the "Open in..." submenu after `open_pr`, and the copy group
   * plus the grouping section after `rename`, inside the existing groups
   * rather than tacking them onto the end of the menu. Each injected node
   * receives no leading separator — it inherits the group of the preceding
   * action (a node that wants its own section supplies its own leading
   * separator, as the grouping section does). Multiple entries may target
   * the same action id; they render in array order.
   */
  injectAfter?: ReadonlyArray<{ actionId: string; content: ReactElement }>;
  /**
   * Radix menu primitives to render through — either the right-click
   * context menu set or the sidebar row's "..." dropdown set, so both
   * surfaces render an identical action list.
   */
  menu: WorkspaceMenuComponents;
};

const renderMenuItems = (props: RenderMenuProps): Array<ReactElement> => {
  const menu = props.menu;
  const visible = props.actions.filter((action) => (action.visible ? action.visible(props.target) : true));

  const out: Array<ReactElement> = [];
  visible.forEach((action, index) => {
    const isFirst = index === 0;
    const isSeparatorVisible = !isFirst && action.separatorBefore === true;
    const isDisabled = action.disabled ? action.disabled(props.target) : false;
    const title = action.getTitle ? action.getTitle(props.target) : action.title;
    out.push(
      <Fragment key={action.id}>
        {isSeparatorVisible ? <menu.Separator /> : null}
        <menu.Item
          data-testid={action.testId}
          color={action.destructive ? props.destructiveColor : undefined}
          disabled={isDisabled}
          onSelect={(): void => {
            void action.perform(props.target);
          }}
        >
          {action.icon ? <action.icon size={ICON_SIZE} /> : null} {title}
        </menu.Item>
      </Fragment>,
    );
    (props.injectAfter ?? [])
      .filter((inj) => inj.actionId === action.id)
      .forEach((inj, i) => {
        out.push(<Fragment key={`__inject_after_${action.id}_${i}`}>{inj.content}</Fragment>);
      });
  });
  return out;
};

/**
 * Slice of `WorkspaceActionRuntime` that the right-click menu needs for
 * the "Open in..." submenu. Kept narrow so callers don't have to plumb the
 * full runtime down for this one feature.
 */
export type OpenInRuntime = {
  openInApp: (workspace: Workspace, app: ExternalApp) => void;
  canOpenInOS: () => boolean;
  isMacUi: () => boolean;
};

/**
 * Builds the rendered workspace-menu rows (descriptor actions + the injected
 * "Open in..." submenu and copy group) for the given Radix menu primitives.
 * Shared by the right-click context menu and the sidebar row's "..." dropdown
 * so the two surfaces render an identical list and cannot drift apart.
 */
const useWorkspaceMenuItems = (
  menu: WorkspaceMenuComponents,
  {
    actions,
    workspace,
    destructiveColor,
    openInRuntime,
  }: {
    actions: ReadonlyArray<WorkspaceAction>;
    workspace: Workspace;
    destructiveColor: AccentColor;
    openInRuntime?: OpenInRuntime;
  },
): Array<ReactElement> => {
  // Branch info is pushed over the WebSocket, so this is a plain atom read
  // (no fetch). Fall back to the source branch when the live branch hasn't
  // arrived yet.
  const branch = useWorkspaceBranch(workspace.objectId)?.currentBranch ?? workspace.sourceBranch ?? null;
  // The grouping section sits just above Delete while the workspace-groups
  // experiment is on (injected after the rename group). Gated by mounting (not
  // by hiding inside the section) so the flag-off menu performs no group-store
  // reads at all.
  const areWorkspaceGroupsEnabled = useAtomValue(isWorkspaceGroupsEnabledAtom);
  const isOpenInVisible =
    openInRuntime != null && openInRuntime.canOpenInOS() && openInRuntime.isMacUi() && getOpenWithItems().length > 0;
  // Render the Open-in submenu inline, immediately after the `open_pr`
  // action — it shares the git/repo group with Commit / Create PR /
  // Open PR. Falls back when the menu has no `open_pr` row
  // (it just won't appear).
  const openInSub = isOpenInVisible ? (
    <menu.Sub>
      <menu.SubTrigger>
        <FolderOpenIcon size={ICON_SIZE} /> Open in...
      </menu.SubTrigger>
      <menu.SubContent>
        {getOpenWithItems().map((item) => (
          <menu.Item key={item.app} onSelect={(): void => openInRuntime.openInApp(workspace, item.app)}>
            <img src={item.icon} alt="" width={ICON_SIZE} height={ICON_SIZE} /> {item.label}
          </menu.Item>
        ))}
      </menu.SubContent>
    </menu.Sub>
  ) : null;
  // Injected into the "Rename" group (right after the rename row, no leading
  // separator). The name lives on the workspace object and the branch is a
  // plain atom read (pushed over the WebSocket), so both copy synchronously;
  // only the opaque id is tucked away in Diagnostics.
  const copyGroup = (
    <>
      <menu.Item
        data-testid={ElementIds.TAB_CONTEXT_MENU_COPY_WORKSPACE_NAME}
        disabled={!workspace.description}
        onSelect={async (): Promise<void> => {
          if (workspace.description) {
            await navigator.clipboard.writeText(workspace.description);
          }
        }}
      >
        <Copy size={14} /> Copy workspace name
      </menu.Item>
      <menu.Item
        data-testid={ElementIds.TAB_CONTEXT_MENU_COPY_BRANCH}
        disabled={!branch}
        onSelect={async (): Promise<void> => {
          if (branch) {
            await navigator.clipboard.writeText(branch);
          }
        }}
      >
        <GitBranch size={14} /> Copy branch
      </menu.Item>
      <menu.Sub>
        <menu.SubTrigger data-testid={ElementIds.TAB_CONTEXT_MENU_DIAGNOSTICS}>
          <Stethoscope size={14} /> Diagnostics
        </menu.SubTrigger>
        <menu.SubContent>
          <menu.Item
            data-testid={ElementIds.TAB_CONTEXT_MENU_COPY_WORKSPACE_ID}
            onSelect={async (): Promise<void> => {
              await navigator.clipboard.writeText(workspace.objectId);
            }}
          >
            Copy workspace id
          </menu.Item>
        </menu.SubContent>
      </menu.Sub>
    </>
  );
  return renderMenuItems({
    actions,
    target: workspace,
    destructiveColor,
    menu,
    injectAfter: [
      ...(openInSub != null ? [{ actionId: "open_pr", content: openInSub }] : []),
      { actionId: "rename", content: copyGroup },
      // Grouping lands after the rename/copy group and before Delete (which
      // brings its own separator); the section supplies its own leading
      // separator. Injected here rather than prepended so it reads as a late,
      // occasional action rather than the menu's headline.
      ...(areWorkspaceGroupsEnabled
        ? [
            {
              actionId: "rename",
              content: <WorkspaceGroupingMenuItems key="workspace-grouping" menu={menu} workspace={workspace} />,
            },
          ]
        : []),
    ],
  });
};

/**
 * The close-time focus handoff shared by both workspace row menu surfaces.
 * Radix restores focus to the trigger when a menu closes, which would blur —
 * and cancel — an inline rename input mounted while the menu was still open. So
 * the Rename action only records intent in `pendingWorkspaceRenameIdAtom`; this
 * handler, run from the menu's `onCloseAutoFocus` after the focus scope is torn
 * down, suppresses the restore and only then enters rename mode, so the input
 * takes focus with nothing competing for it. The `preventDefault` is
 * unconditional — these menus never want focus bounced back to the row after a
 * copy/diagnostics action either. See the `use_close_auto_focus_for_focus_handoff`
 * review rule.
 */
const useWorkspaceMenuCloseAutoFocus = (): ((event: Event) => void) => {
  const store = useStore();
  return (event: Event): void => {
    event.preventDefault();
    const pendingId = store.get(pendingWorkspaceRenameIdAtom);
    if (pendingId !== null) {
      store.set(pendingWorkspaceRenameIdAtom, null);
      store.set(renamingWorkspaceIdAtom, pendingId);
    }
  };
};

export const WorkspaceContextMenuContent = ({
  actions,
  workspace,
  destructiveColor,
  openInRuntime,
}: {
  actions: ReadonlyArray<WorkspaceAction>;
  workspace: Workspace;
  destructiveColor: AccentColor;
  /**
   * When provided AND the runtime reports the capability is available,
   * an "Open in..." submenu is appended after the action list. When
   * absent the submenu is omitted entirely.
   */
  openInRuntime?: OpenInRuntime;
}): ReactElement => {
  const items = useWorkspaceMenuItems(CONTEXT_MENU_COMPONENTS, {
    actions,
    workspace,
    destructiveColor,
    openInRuntime,
  });
  const onCloseAutoFocus = useWorkspaceMenuCloseAutoFocus();
  return (
    <ContextMenu.Content size="1" onCloseAutoFocus={onCloseAutoFocus}>
      {items}
    </ContextMenu.Content>
  );
};

/**
 * The sidebar workspace row's "..." dropdown. Renders the exact same action
 * list as the right-click context menu (`WorkspaceContextMenuContent`),
 * including the "Open in..." submenu and the copy/diagnostics group, so the
 * two entry points never diverge.
 */
export const WorkspaceDropdownMenuContent = ({
  actions,
  workspace,
  destructiveColor,
  openInRuntime,
}: {
  actions: ReadonlyArray<WorkspaceAction>;
  workspace: Workspace;
  destructiveColor: AccentColor;
  openInRuntime?: OpenInRuntime;
}): ReactElement => {
  const items = useWorkspaceMenuItems(DROPDOWN_MENU_COMPONENTS, {
    actions,
    workspace,
    destructiveColor,
    openInRuntime,
  });
  const onCloseAutoFocus = useWorkspaceMenuCloseAutoFocus();
  return (
    <DropdownMenu.Content size="1" onCloseAutoFocus={onCloseAutoFocus}>
      {items}
    </DropdownMenu.Content>
  );
};
