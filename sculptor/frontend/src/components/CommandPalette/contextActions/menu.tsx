import { ContextMenu, DropdownMenu } from "@radix-ui/themes";
import { Copy, FolderOpenIcon, GitBranch, Stethoscope } from "lucide-react";
import type { ComponentType, ReactElement, ReactNode } from "react";
import { Fragment } from "react";

import { ElementIds, type ExternalApp, type Workspace } from "../../../api";
import { getOpenWithItems } from "../../../common/openInApp/items.tsx";
import type { AccentColor } from "../../../common/state/atoms/themeBuilder";
import { useWorkspaceBranch } from "../../../common/state/hooks/useWorkspaceBranch.ts";
import type { Agent, AgentAction, ContextActionShared, WorkspaceAction } from "./types.ts";

/** Pixel size shared by every icon rendered in these context menus. */
const ICON_SIZE = 14;

/**
 * The Radix menu primitives the workspace menu body renders through.
 * `ContextMenu.*` and `DropdownMenu.*` expose the same sub-API with
 * compatible props, so the same body can render into either the
 * right-click context menu or the sidebar row's "..." dropdown — keeping
 * the two menus in lockstep instead of maintaining two divergent lists.
 */
type WorkspaceMenuComponents = {
  Item: ComponentType<{
    "data-testid"?: string;
    color?: AccentColor;
    disabled?: boolean;
    onSelect?: (event: Event) => void;
    children?: ReactNode;
  }>;
  Separator: ComponentType;
  Sub: ComponentType<{ children?: ReactNode }>;
  SubTrigger: ComponentType<{ "data-testid"?: string; children?: ReactNode }>;
  SubContent: ComponentType<{ children?: ReactNode }>;
};

const CONTEXT_MENU_COMPONENTS: WorkspaceMenuComponents = {
  Item: ContextMenu.Item as WorkspaceMenuComponents["Item"],
  Separator: ContextMenu.Separator as WorkspaceMenuComponents["Separator"],
  Sub: ContextMenu.Sub as WorkspaceMenuComponents["Sub"],
  SubTrigger: ContextMenu.SubTrigger as WorkspaceMenuComponents["SubTrigger"],
  SubContent: ContextMenu.SubContent as WorkspaceMenuComponents["SubContent"],
};

const DROPDOWN_MENU_COMPONENTS: WorkspaceMenuComponents = {
  Item: DropdownMenu.Item as WorkspaceMenuComponents["Item"],
  Separator: DropdownMenu.Separator as WorkspaceMenuComponents["Separator"],
  Sub: DropdownMenu.Sub as WorkspaceMenuComponents["Sub"],
  SubTrigger: DropdownMenu.SubTrigger as WorkspaceMenuComponents["SubTrigger"],
  SubContent: DropdownMenu.SubContent as WorkspaceMenuComponents["SubContent"],
};

/**
 * The slice of an action descriptor the right-click menu reads, narrowed to
 * the menu's target entity. Both `WorkspaceAction` and `AgentAction` satisfy
 * this for `Workspace` and `Agent` respectively, letting `renderMenuItems`
 * stay generic over the target without per-field type assertions.
 */
type TargetedAction<TTarget> = ContextActionShared & {
  visible?: (target: TTarget) => boolean;
  disabled?: (target: TTarget) => boolean;
  getTitle?: (target: TTarget) => string;
  perform: (target: TTarget) => void | Promise<void>;
};

type RenderMenuProps<TTarget> = {
  actions: ReadonlyArray<TargetedAction<TTarget>>;
  target: TTarget;
  /**
   * Radix accent color for destructive actions. Workspace tabs derive
   * this from the active theme builder; agent tabs use the literal "red".
   */
  destructiveColor: AccentColor;
  /**
   * Returns the perform handler for a given action. Kept narrow so the
   * underlying action.perform signature stays typed against its target.
   */
  performFor: (action: TargetedAction<TTarget>) => () => void | Promise<void>;
  /**
   * Optional content to splice into the rendered menu immediately after
   * the action with the given id. Used by `WorkspaceContextMenuContent`
   * to inject the "Open in..." submenu after `open_pr` and the copy group
   * after `rename`, inside the existing groups rather than tacking them
   * onto the end of the menu. Each injected node receives no leading
   * separator — it inherits the group of the preceding action. Multiple
   * entries may target the same action id; they render in array order.
   */
  injectAfter?: ReadonlyArray<{ actionId: string; content: ReactElement }>;
  /**
   * Radix menu primitives to render through. Defaults to the right-click
   * context menu; the sidebar row's "..." dropdown passes the dropdown set
   * so both surfaces render the identical action list.
   */
  menu?: WorkspaceMenuComponents;
};

const renderMenuItems = <TTarget,>(props: RenderMenuProps<TTarget>): Array<ReactElement> => {
  const menu = props.menu ?? CONTEXT_MENU_COMPONENTS;
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
            // performFor is curried — it returns the actual handler.
            // Forgetting the trailing () silently builds the function and
            // throws it away, leaving every menu item a no-op.
            void props.performFor(action)();
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
  // arrived yet — mirrors how `ClosedWorkspaceRow` picks a branch to show.
  const branch = useWorkspaceBranch(workspace.objectId)?.currentBranch ?? workspace.sourceBranch ?? null;
  const isOpenInVisible =
    openInRuntime != null && openInRuntime.canOpenInOS() && openInRuntime.isMacUi() && getOpenWithItems().length > 0;
  // Render the Open-in submenu inline, immediately after the `open_pr`
  // action — it shares the git/repo group with Commit / Create MR /
  // Open MR. Falls back when the menu has no `open_pr` row
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
  return renderMenuItems<Workspace>({
    actions,
    target: workspace,
    destructiveColor,
    menu,
    performFor: (action) => (): void | Promise<void> => action.perform(workspace),
    injectAfter: [
      ...(openInSub != null ? [{ actionId: "open_pr", content: openInSub }] : []),
      { actionId: "rename", content: copyGroup },
    ],
  });
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
  return (
    <ContextMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
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
  return (
    <DropdownMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
      {items}
    </DropdownMenu.Content>
  );
};

export const AgentContextMenuContent = ({
  actions,
  agent,
  trailing,
}: {
  actions: ReadonlyArray<AgentAction>;
  agent: Agent;
  trailing?: ReactElement;
}): ReactElement => {
  // Copy name + the Diagnostics submenu (`trailing`) are injected right after
  // "Mark unread" (no leading separator) so they sit in the top group above
  // the divider that sets the destructive Delete apart on its own.
  const copyName = (
    <ContextMenu.Item
      data-testid={ElementIds.TAB_CONTEXT_MENU_COPY_AGENT_NAME}
      disabled={!agent.title}
      onSelect={async (): Promise<void> => {
        if (agent.title) {
          await navigator.clipboard.writeText(agent.title);
        }
      }}
    >
      <Copy size={14} /> Copy agent name
    </ContextMenu.Item>
  );
  return (
    <ContextMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
      {renderMenuItems<Agent>({
        actions,
        target: agent,
        destructiveColor: "red",
        performFor: (action) => (): void | Promise<void> => action.perform(agent),
        injectAfter: [
          { actionId: "mark_unread", content: copyName },
          ...(trailing != null ? [{ actionId: "mark_unread", content: trailing }] : []),
        ],
      })}
    </ContextMenu.Content>
  );
};
