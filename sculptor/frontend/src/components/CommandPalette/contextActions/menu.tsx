import { ContextMenu } from "@radix-ui/themes";
import { Copy, FolderOpenIcon, GitBranch, Stethoscope } from "lucide-react";
import type { ReactElement } from "react";
import { Fragment } from "react";

import { ElementIds, type ExternalApp, type Workspace } from "../../../api";
import { getOpenWithItems } from "../../../common/openInApp/items.tsx";
import type { AccentColor } from "../../../common/state/atoms/themeBuilder";
import { useWorkspaceBranch } from "../../../common/state/hooks/useWorkspaceBranch.ts";
import type { Agent, AgentAction, ContextActionShared, WorkspaceAction } from "./types.ts";

/** Pixel size shared by every icon rendered in these context menus. */
const ICON_SIZE = 14;

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
};

const renderMenuItems = <TTarget,>(props: RenderMenuProps<TTarget>): Array<ReactElement> => {
  const visible = props.actions.filter((action) => (action.visible ? action.visible(props.target) : true));

  const out: Array<ReactElement> = [];
  visible.forEach((action, index) => {
    const isFirst = index === 0;
    const isSeparatorVisible = !isFirst && action.separatorBefore === true;
    const isDisabled = action.disabled ? action.disabled(props.target) : false;
    const title = action.getTitle ? action.getTitle(props.target) : action.title;
    out.push(
      <Fragment key={action.id}>
        {isSeparatorVisible ? <ContextMenu.Separator /> : null}
        <ContextMenu.Item
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
        </ContextMenu.Item>
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
  // Branch info is pushed over the WebSocket, so this is a plain atom read
  // (no fetch). Fall back to the source branch when the live branch hasn't
  // arrived yet — mirrors how `ClosedWorkspaceRow` picks a branch to show.
  const branch = useWorkspaceBranch(workspace.objectId)?.currentBranch ?? workspace.sourceBranch ?? null;
  const isOpenInVisible =
    openInRuntime != null && openInRuntime.canOpenInOS() && openInRuntime.isMacUi() && getOpenWithItems().length > 0;
  // Render the Open-in submenu inline, immediately after the `open_pr`
  // action — it shares the git/repo group with Commit / Create PR /
  // Open PR. Falls back when the menu has no `open_pr` row
  // (it just won't appear).
  const openInSub = isOpenInVisible ? (
    <ContextMenu.Sub>
      <ContextMenu.SubTrigger>
        <FolderOpenIcon size={ICON_SIZE} /> Open in...
      </ContextMenu.SubTrigger>
      <ContextMenu.SubContent>
        {getOpenWithItems().map((item) => (
          <ContextMenu.Item key={item.app} onSelect={(): void => openInRuntime.openInApp(workspace, item.app)}>
            <img src={item.icon} alt="" width={ICON_SIZE} height={ICON_SIZE} /> {item.label}
          </ContextMenu.Item>
        ))}
      </ContextMenu.SubContent>
    </ContextMenu.Sub>
  ) : null;
  // Injected into the "Rename" group (right after the rename row, no leading
  // separator). The name lives on the workspace object and the branch is a
  // plain atom read (pushed over the WebSocket), so both copy synchronously;
  // only the opaque id is tucked away in Diagnostics.
  const copyGroup = (
    <>
      <ContextMenu.Item
        data-testid={ElementIds.TAB_CONTEXT_MENU_COPY_WORKSPACE_NAME}
        disabled={!workspace.description}
        onSelect={async (): Promise<void> => {
          if (workspace.description) {
            await navigator.clipboard.writeText(workspace.description);
          }
        }}
      >
        <Copy size={14} /> Copy workspace name
      </ContextMenu.Item>
      <ContextMenu.Item
        data-testid={ElementIds.TAB_CONTEXT_MENU_COPY_BRANCH}
        disabled={!branch}
        onSelect={async (): Promise<void> => {
          if (branch) {
            await navigator.clipboard.writeText(branch);
          }
        }}
      >
        <GitBranch size={14} /> Copy branch
      </ContextMenu.Item>
      <ContextMenu.Sub>
        <ContextMenu.SubTrigger data-testid={ElementIds.TAB_CONTEXT_MENU_DIAGNOSTICS}>
          <Stethoscope size={14} /> Diagnostics
        </ContextMenu.SubTrigger>
        <ContextMenu.SubContent>
          <ContextMenu.Item
            data-testid={ElementIds.TAB_CONTEXT_MENU_COPY_WORKSPACE_ID}
            onSelect={async (): Promise<void> => {
              await navigator.clipboard.writeText(workspace.objectId);
            }}
          >
            Copy workspace id
          </ContextMenu.Item>
        </ContextMenu.SubContent>
      </ContextMenu.Sub>
    </>
  );
  return (
    <ContextMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
      {renderMenuItems<Workspace>({
        actions,
        target: workspace,
        destructiveColor,
        performFor: (action) => (): void | Promise<void> => action.perform(workspace),
        injectAfter: [
          ...(openInSub != null ? [{ actionId: "open_pr", content: openInSub }] : []),
          { actionId: "rename", content: copyGroup },
        ],
      })}
    </ContextMenu.Content>
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
