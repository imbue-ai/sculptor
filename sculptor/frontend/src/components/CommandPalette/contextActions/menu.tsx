import { ContextMenu } from "@radix-ui/themes";
import { Copy, FolderOpenIcon, GitBranch, Stethoscope } from "lucide-react";
import type { ReactElement } from "react";
import { Fragment } from "react";

import { ElementIds, type ExternalApp, type Workspace } from "../../../api";
import { getOpenWithItems } from "../../../common/openInApp/items.tsx";
import type { AccentColor } from "../../../common/state/atoms/themeBuilder";
import { useWorkspaceBranch } from "../../../common/state/hooks/useWorkspaceBranch.ts";
import type { Agent, AgentAction, ContextActionShared, WorkspaceAction } from "./types.ts";

type RenderMenuProps<TAction extends ContextActionShared, TTarget> = {
  actions: ReadonlyArray<TAction>;
  target: TTarget;
  /**
   * Radix accent color for destructive actions. Workspace tabs derive
   * this from the active theme builder; agent tabs use the literal "red".
   */
  destructiveColor: AccentColor;
  /**
   * Optional trailing content (e.g. the Diagnostics submenu) appended
   * after the action list. The Diagnostics submenu has async data needs
   * that the registry doesn't model.
   */
  trailing?: ReactElement;
  /**
   * Returns the perform handler for a given action. Kept narrow so the
   * underlying action.perform signature stays typed against its target.
   */
  performFor: (action: TAction) => () => void | Promise<void>;
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

const renderMenuItems = <TAction extends ContextActionShared, TTarget>(
  props: RenderMenuProps<TAction, TTarget>,
): Array<ReactElement> => {
  const visible = props.actions.filter((a) => {
    const v = (a as { visible?: (t: TTarget) => boolean }).visible;
    return v ? v(props.target) : true;
  });

  const out: Array<ReactElement> = [];
  visible.forEach((action, index) => {
    const isFirst = index === 0;
    const isSeparatorVisible = !isFirst && action.separatorBefore === true;
    const disabledFn = (action as { disabled?: (t: TTarget) => boolean }).disabled;
    const isDisabled = disabledFn ? disabledFn(props.target) : false;
    const getTitleFn = (action as { getTitle?: (t: TTarget) => string }).getTitle;
    const title = getTitleFn ? getTitleFn(props.target) : action.title;
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
          {action.icon ? <action.icon size={14} /> : null} {title}
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
  // action — it shares the git/repo group with Commit / Create MR /
  // Open MR. Falls back when the menu has no `open_pr` row
  // (it just won't appear).
  const openInSub = isOpenInVisible ? (
    <ContextMenu.Sub>
      <ContextMenu.SubTrigger>
        <FolderOpenIcon size={14} /> Open in...
      </ContextMenu.SubTrigger>
      <ContextMenu.SubContent>
        {getOpenWithItems().map((item) => (
          <ContextMenu.Item key={item.app} onSelect={(): void => openInRuntime.openInApp(workspace, item.app)}>
            <img src={item.icon} alt="" width={14} height={14} /> {item.label}
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
      {renderMenuItems<WorkspaceAction, Workspace>({
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
      {renderMenuItems<AgentAction, Agent>({
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
