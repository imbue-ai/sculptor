import { Flex, Text } from "@radix-ui/themes";
import classnames from "classnames";
import { useAtomValue, useSetAtom } from "jotai";
import { Folder } from "lucide-react";
import type { ComponentType, ElementType, MouseEvent, ReactElement, ReactNode } from "react";
import { createElement, useCallback } from "react";
import { useParams } from "react-router-dom";

import { ElementIds } from "~/api";
import { useImbueNavigate } from "~/common/hooks/navigation";
import { projectAtomFamily } from "~/common/state/atoms/projects";
import { taskAtomFamily } from "~/common/state/atoms/tasks";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces";
import { openFileViewTabAtom } from "~/pages/workspace/diffPanel/atoms/diffPanel";
import { revealFolderAtom } from "~/pages/workspace/panels/fileBrowser/atoms/fileBrowser";
import { getFileIcon } from "~/pages/workspace/panels/fileBrowser/fileIcons";

import { type SkillType } from "../common/utils/skillBadge";
import styles from "./editor/MentionNodeView.module.scss";
import { TYPE_ICONS } from "./EntityMentionSuggestion";
import { HoverCard } from "./HoverCard";
import entityStyles from "./MentionChip.module.scss";
import { AgentDetailPane } from "./mentionDetailPanes/AgentDetailPane";
import { RepositoryDetailPane } from "./mentionDetailPanes/RepositoryDetailPane";
import { WorkspaceDetailPane } from "./mentionDetailPanes/WorkspaceDetailPane";
import { SkillHoverContent } from "./skills/SkillHoverContent";

const ICON_STYLE = { width: "calc(1em - 1px)", height: "calc(1em - 1px)" };
const HOVER_GROUP = "chat-mention-chips";

type EntityType = "repository" | "workspace" | "agent";

type SharedChipProps = {
  // Element used for the chip trigger. Tiptap's MentionNodeView passes
  // NodeViewWrapper here so tiptap can manage the node lifecycle; other
  // callers (e.g. rendering sent user messages) let this default to "span".
  wrapperElement?: ElementType | ComponentType<Record<string, unknown>>;
  wrapperProps?: Record<string, unknown>;
  // Forces the hover card open — set by the editor node view when the chip
  // is node-selected so keyboard navigation surfaces the same popover as
  // hovering with the mouse.
  selected?: boolean;
  // Suppresses hover-open while the chip sits inside an active range
  // selection in the editor (e.g. Cmd+A), so a selection doesn't fan out
  // every popover as the mouse moves across chips.
  suppressHover?: boolean;
  // For file/folder chips: an override label used when two chips in the
  // same input share a basename (e.g. `.claude/.../create-html-mock` instead
  // of a bare `create-html-mock` that's indistinguishable from its sibling).
  // Skill and entity chips ignore it. Lives on the shared props because
  // MentionNodeView passes a single union-typed object to MentionChip and
  // lets the dispatcher pick the variant.
  displayLabel?: string | null;
};

export type MentionChipProps =
  | ({
      kind?: "file";
      id: string;
    } & SharedChipProps)
  | ({
      kind?: "skill";
      id: string;
      skillDescription?: string | null;
      skillType?: SkillType | null;
    } & SharedChipProps)
  | ({
      kind: "entity";
      entityType: EntityType;
      entityId: string;
      entityDisplayName: string;
    } & SharedChipProps);

type WrapperElement = NonNullable<SharedChipProps["wrapperElement"]>;

const getDisplayInfo = (id: string): { displayName: string; isDirectory: boolean } => {
  const path = id.startsWith("@") ? id.slice(1) : id;
  const isDirectory = path.endsWith("/");
  const normalised = isDirectory ? path.slice(0, -1) : path;
  const lastSlash = normalised.lastIndexOf("/");
  const baseName = lastSlash === -1 ? normalised : normalised.slice(lastSlash + 1);
  return { displayName: baseName, isDirectory };
};

type ChipHoverCardProps = {
  trigger: ReactNode;
  content: ReactNode;
  selected?: boolean;
  suppressHover?: boolean;
};

// Wrapper around `HoverCard` that pre-applies the "chat mention chips" group
// and geometry so every subcomponent in this file shares identical hover
// behaviour (group coordination, sideOffset, forceOpen plumbing).
const ChipHoverCard = ({ trigger, content, selected, suppressHover }: ChipHoverCardProps): ReactElement => (
  <HoverCard
    group={HOVER_GROUP}
    side="top"
    align="start"
    sideOffset={4}
    alignOffset={-8}
    forceOpen={selected}
    suppressHover={suppressHover}
    trigger={trigger}
    content={content}
  />
);

const SkillMentionChip = ({
  id,
  skillDescription,
  skillType,
  Wrapper,
  wrapperProps,
  selected,
  suppressHover,
}: {
  id: string;
  skillDescription?: string | null;
  skillType?: SkillType | null;
  Wrapper: WrapperElement;
  wrapperProps?: Record<string, unknown>;
  selected?: boolean;
  suppressHover?: boolean;
}): ReactElement => (
  <ChipHoverCard
    selected={selected}
    suppressHover={suppressHover}
    trigger={
      <Wrapper {...wrapperProps} className={styles.mention} data-testid={ElementIds.MENTION_SPAN}>
        {id}
      </Wrapper>
    }
    content={<SkillHoverContent id={id} skillDescription={skillDescription} skillType={skillType} />}
  />
);

const FileMentionChip = ({
  id,
  displayLabel,
  Wrapper,
  wrapperProps,
  selected,
  suppressHover,
}: {
  id: string;
  displayLabel?: string | null;
  Wrapper: WrapperElement;
  wrapperProps?: Record<string, unknown>;
  selected?: boolean;
  suppressHover?: boolean;
}): ReactElement => {
  const { workspaceID } = useParams<{ workspaceID?: string }>();
  const openFileViewTab = useSetAtom(openFileViewTabAtom);
  const revealFolder = useSetAtom(revealFolderAtom);

  const { displayName: basename, isDirectory } = getDisplayInfo(id);
  // Pick the file-type icon from the basename even when an override is in
  // play — the override carries path segments that would confuse getFileIcon.
  const Icon = isDirectory ? Folder : getFileIcon(basename);
  const visibleLabel = displayLabel ?? basename;
  const displayPath = id.startsWith("@") ? id.slice(1) : id;
  // Outside a workspace route there is nowhere to open the file/folder, so the
  // chip renders inert rather than as a pointer-cursor control that silently
  // drops the click (matches the EntityMentionChip pattern from SCU-1215).
  const isClickable = Boolean(workspaceID);

  const handleClick = useCallback(
    (e: MouseEvent) => {
      if (!workspaceID) return;
      e.stopPropagation();
      const path = id.startsWith("@") ? id.slice(1) : id;
      if (isDirectory) {
        revealFolder({ workspaceId: workspaceID, path });
      } else {
        openFileViewTab({ workspaceId: workspaceID, filePath: path });
      }
    },
    [id, isDirectory, workspaceID, openFileViewTab, revealFolder],
  );

  return (
    <ChipHoverCard
      selected={selected}
      suppressHover={suppressHover}
      trigger={
        <Wrapper
          {...wrapperProps}
          className={isClickable ? styles.clickableMention : styles.mention}
          data-testid={ElementIds.MENTION_SPAN}
          onClick={isClickable ? handleClick : undefined}
          aria-disabled={isClickable ? undefined : true}
        >
          {createElement(Icon, { style: ICON_STYLE })}
          {/* `direction: rtl` on the label produces start-truncation when the
            chip caps at max-width, preserving the basename (the part users
            scan for) on the right and ellipsizing the disambiguating prefix
            on the left. The hover card still shows the full path. */}
          <span className={styles.fileLabel}>{visibleLabel}</span>
        </Wrapper>
      }
      content={
        <Flex
          direction="column"
          gap="1"
          style={{
            padding: "var(--space-1) var(--space-2)",
            // Allow long paths to grow up to 720px on one line, but never
            // wider than the space Radix has measured between the trigger
            // and the viewport edge — `--radix-popper-available-width` is
            // set on the Content element by Radix Popper.
            maxWidth: "min(720px, var(--radix-popper-available-width, 100vw))",
            minWidth: 0,
          }}
        >
          <Flex align="start" gap="1" style={{ minWidth: 0 }}>
            {createElement(Icon, {
              style: { ...ICON_STYLE, flexShrink: 0, color: "var(--gray-12)", marginTop: "2px" },
            })}
            <Text
              as="div"
              size="1"
              style={{
                fontFamily: "var(--code-font-family)",
                color: "var(--gray-12)",
                minWidth: 0,
                wordBreak: "break-all",
              }}
            >
              {displayPath}
            </Text>
          </Flex>
          <Text as="div" size="1" style={{ color: "var(--gray-10)" }}>
            {isDirectory ? "Click to reveal in file browser" : "Click to open"}
          </Text>
        </Flex>
      }
    />
  );
};

// Per-entity-type detail pane, used both as this chip's HoverCard content and
// as the entity picker's right-hand pane. Keeping the routing in one place
// here means a future fourth entity type is a single-switch change.
const EntityDetailPane = ({
  entityType,
  entityId,
  entityDisplayName,
}: {
  entityType: EntityType;
  entityId: string;
  entityDisplayName: string;
}): ReactElement => {
  switch (entityType) {
    case "agent":
      return <AgentDetailPane agentId={entityId} entityDisplayName={entityDisplayName} />;
    case "workspace":
      return <WorkspaceDetailPane workspaceId={entityId} entityDisplayName={entityDisplayName} />;
    case "repository":
      return <RepositoryDetailPane projectId={entityId} entityDisplayName={entityDisplayName} />;
  }
};

const EntityMentionChip = ({
  entityType,
  entityId,
  entityDisplayName,
  Wrapper,
  wrapperProps,
  selected,
  suppressHover,
}: {
  entityType: EntityType;
  entityId: string;
  entityDisplayName: string;
  Wrapper: WrapperElement;
  wrapperProps?: Record<string, unknown>;
  selected?: boolean;
  suppressHover?: boolean;
}): ReactElement => {
  // Subscribe only to the primary atom that matters for this entityType —
  // the null-check drives `isDeleted`. The hover card's detail pane pulls
  // the richer composite atom (`agentDetailAtomFamily` etc.) on its own;
  // doing that here would re-render the chip on every contributing-atom
  // change. The unused keys (e.g. projectAtomFamily for an agent chip) are
  // gated to "" so Jotai's atomFamily doesn't create new instances per id.
  const project = useAtomValue(projectAtomFamily(entityType === "repository" ? entityId : ""));
  const workspace = useAtomValue(workspaceAtomFamily(entityType === "workspace" ? entityId : ""));
  const task = useAtomValue(taskAtomFamily(entityType === "agent" ? entityId : ""));

  const isDeleted =
    entityType === "repository" ? project === null : entityType === "workspace" ? workspace === null : task === null;

  const { navigateToWorkspace, navigateToAgent } = useImbueNavigate();
  // Repository chips and deleted entities never navigate. They render as inert
  // label chips with no click handler at all — not a handler gated by an
  // internal early-return — so the chip is honest about being non-interactive
  // instead of silently dropping a click (SCU-1215).
  const isClickable = !isDeleted && entityType !== "repository";
  const Icon = TYPE_ICONS[entityType];

  const handleClick = useCallback(
    (e: MouseEvent): void => {
      e.stopPropagation();
      e.preventDefault();
      if (entityType === "workspace") {
        navigateToWorkspace(entityId);
      } else if (entityType === "agent" && task?.workspaceId != null) {
        navigateToAgent(task.workspaceId, entityId);
      }
    },
    [entityType, entityId, navigateToWorkspace, navigateToAgent, task?.workspaceId],
  );

  return (
    <ChipHoverCard
      selected={selected}
      suppressHover={suppressHover}
      trigger={
        <Wrapper
          {...wrapperProps}
          className={classnames(
            // Reuse the `@`-chip palette so every chip family (file, folder,
            // skill, entity) shares one accent scheme. Entity type reads off
            // the leading icon and the `data-entity-type` attribute.
            isClickable ? styles.clickableMention : styles.mention,
            entityStyles.entityChip,
            isDeleted && entityStyles.deleted,
          )}
          onClick={isClickable ? handleClick : undefined}
          title={entityDisplayName}
          data-testid={ElementIds.ENTITY_MENTION_CHIP}
          data-entity-type={entityType}
          data-entity-deleted={isDeleted ? "" : undefined}
        >
          <Icon className={entityStyles.icon} aria-hidden />
          <span className={classnames(entityStyles.displayName, isDeleted && entityStyles.strikethrough)}>
            {entityDisplayName}
          </span>
        </Wrapper>
      }
      content={<EntityDetailPane entityType={entityType} entityId={entityId} entityDisplayName={entityDisplayName} />}
    />
  );
};

// `kind` is optional for file / skill callers because the legacy call sites
// pass only an `id` string; inferring from the leading character preserves
// back-compat with zero caller churn.
const resolveKind = (props: MentionChipProps): "file" | "skill" | "entity" => {
  if (props.kind !== undefined) return props.kind;
  return "id" in props && props.id.startsWith("/") ? "skill" : "file";
};

export const MentionChip = (props: MentionChipProps): ReactElement => {
  const Wrapper = (props.wrapperElement ?? "span") as WrapperElement;
  const kind = resolveKind(props);

  if (kind === "entity") {
    const entityProps = props as Extract<MentionChipProps, { kind: "entity" }>;
    return (
      <EntityMentionChip
        entityType={entityProps.entityType}
        entityId={entityProps.entityId}
        entityDisplayName={entityProps.entityDisplayName}
        Wrapper={Wrapper}
        wrapperProps={entityProps.wrapperProps}
        selected={entityProps.selected}
        suppressHover={entityProps.suppressHover}
      />
    );
  }

  if (kind === "skill") {
    const skillProps = props as Extract<MentionChipProps, { kind?: "skill"; id: string }> & {
      skillDescription?: string | null;
      skillType?: SkillType | null;
    };
    return (
      <SkillMentionChip
        id={skillProps.id}
        skillDescription={skillProps.skillDescription}
        skillType={skillProps.skillType}
        Wrapper={Wrapper}
        wrapperProps={skillProps.wrapperProps}
        selected={skillProps.selected}
        suppressHover={skillProps.suppressHover}
      />
    );
  }

  const fileProps = props as Extract<MentionChipProps, { kind?: "file"; id: string }>;
  return (
    <FileMentionChip
      id={fileProps.id}
      displayLabel={fileProps.displayLabel}
      Wrapper={Wrapper}
      wrapperProps={fileProps.wrapperProps}
      selected={fileProps.selected}
      suppressHover={fileProps.suppressHover}
    />
  );
};
