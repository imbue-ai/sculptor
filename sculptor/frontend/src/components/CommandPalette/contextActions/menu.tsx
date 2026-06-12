import { ContextMenu, DropdownMenu } from "@radix-ui/themes";
import { FolderOpenIcon } from "lucide-react";
import type { ReactElement } from "react";
import { Fragment } from "react";

import type { ExternalApp, Workspace } from "../../../api";
import { getOpenWithItems } from "../../../common/openInApp/items.tsx";
import type { AccentColor } from "../../../common/state/atoms/themeBuilder";
import type { Agent, AgentAction, ContextActionShared, WorkspaceAction } from "./types.ts";

/**
 * Radix's ContextMenu and DropdownMenu expose the same item primitives. The
 * menu bodies below are rendered through this union so the same action list
 * can back both the right-click menu and click-triggered "..." dropdowns.
 */
type MenuKit = typeof ContextMenu | typeof DropdownMenu;

type RenderMenuProps<TAction extends ContextActionShared, TTarget> = {
  menu: MenuKit;
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
   * to inject the "Open in..." submenu inside the existing group rather
   * than tacking it onto the end of the menu. The injected node receives
   * no leading separator — it inherits the group of the preceding action.
   */
  injectAfter?: { actionId: string; content: ReactElement };
};

const renderMenuItems = <TAction extends ContextActionShared, TTarget>(
  props: RenderMenuProps<TAction, TTarget>,
): Array<ReactElement> => {
  const { Item, Separator } = props.menu;
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
        {isSeparatorVisible ? <Separator /> : null}
        <Item
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
        </Item>
      </Fragment>,
    );
    if (props.injectAfter && props.injectAfter.actionId === action.id) {
      out.push(<Fragment key={`__inject_after_${action.id}`}>{props.injectAfter.content}</Fragment>);
    }
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

type WorkspaceMenuProps = {
  actions: ReadonlyArray<WorkspaceAction>;
  workspace: Workspace;
  destructiveColor: AccentColor;
  /**
   * When provided AND the runtime reports the capability is available,
   * an "Open in..." submenu is appended after the action list. When
   * absent the submenu is omitted entirely.
   */
  openInRuntime?: OpenInRuntime;
};

const WorkspaceMenuItems = ({
  menu,
  actions,
  workspace,
  destructiveColor,
  openInRuntime,
}: WorkspaceMenuProps & { menu: MenuKit }): ReactElement => {
  const { Item, Sub, SubTrigger, SubContent } = menu;
  const isOpenInVisible =
    openInRuntime != null && openInRuntime.canOpenInOS() && openInRuntime.isMacUi() && getOpenWithItems().length > 0;
  // Render the Open-in submenu inline, immediately after the `open_pr`
  // action — it shares the git/repo group with Commit / Create MR /
  // Open MR. Falls back when the menu has no `open_pr` row
  // (it just won't appear).
  const openInSub = isOpenInVisible ? (
    <Sub>
      <SubTrigger>
        <FolderOpenIcon size={14} /> Open in...
      </SubTrigger>
      <SubContent>
        {getOpenWithItems().map((item) => (
          <Item key={item.app} onSelect={(): void => openInRuntime.openInApp(workspace, item.app)}>
            <img src={item.icon} alt="" width={14} height={14} /> {item.label}
          </Item>
        ))}
      </SubContent>
    </Sub>
  ) : null;
  return (
    <>
      {renderMenuItems<WorkspaceAction, Workspace>({
        menu,
        actions,
        target: workspace,
        destructiveColor,
        performFor: (action) => (): void | Promise<void> => action.perform(workspace),
        injectAfter: openInSub != null ? { actionId: "open_pr", content: openInSub } : undefined,
      })}
    </>
  );
};

export const WorkspaceContextMenuContent = (props: WorkspaceMenuProps): ReactElement => (
  <ContextMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
    <WorkspaceMenuItems menu={ContextMenu} {...props} />
  </ContextMenu.Content>
);

/**
 * The same workspace action menu as `WorkspaceContextMenuContent`, but for a
 * click-triggered dropdown (e.g. the "..." button on sidebar workspace rows).
 */
export const WorkspaceDropdownMenuContent = (props: WorkspaceMenuProps): ReactElement => (
  <DropdownMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
    <WorkspaceMenuItems menu={DropdownMenu} {...props} />
  </DropdownMenu.Content>
);

export const AgentContextMenuContent = ({
  actions,
  agent,
  trailing,
}: {
  actions: ReadonlyArray<AgentAction>;
  agent: Agent;
  trailing?: ReactElement;
}): ReactElement => {
  return (
    <ContextMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
      {renderMenuItems<AgentAction, Agent>({
        menu: ContextMenu,
        actions,
        target: agent,
        destructiveColor: "red",
        performFor: (action) => (): void | Promise<void> => action.perform(agent),
      })}
      {trailing != null ? (
        <>
          <ContextMenu.Separator />
          {trailing}
        </>
      ) : null}
    </ContextMenu.Content>
  );
};
