import * as Dialog from "@radix-ui/react-dialog";
import { Select, VisuallyHidden } from "@radix-ui/themes";
import { Command } from "cmdk";
import { useAtom, useAtomValue } from "jotai";
import { ChevronRight, MessageSquarePlus, Search, SquareTerminal, X } from "lucide-react";
import type { KeyboardEvent, ReactElement, ReactNode, RefObject } from "react";
import { useCallback, useRef, useState } from "react";

import { type AgentTypeName, ElementIds } from "~/api";
import {
  AGENT_TYPE_LABELS,
  type AgentRegistrationLabel,
  agentTypeDisplayLabel,
  encodeRegisteredAgentType,
  type StoredAgentType,
} from "~/common/state/atoms/agentTabs.ts";
import { isPiAgentEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";
import { PaletteFooter } from "~/components/CommandPalette/PaletteFooter.tsx";
import { addPanelTargetZoneAtom } from "~/components/panels/addPanelAtoms.ts";
import { inSentence, useDestinationSections } from "~/components/panels/destinations.ts";
import type { PanelDefinition, ZoneId } from "~/components/panels/types.ts";
import { useAddPanelMenu } from "~/pages/workspace/panels/useAddPanelMenu.ts";

import styles from "./AddPanelPalette.module.scss";

type PalettePage = "root" | "agents" | "terminals" | "new-agent";

const PAGE_BREADCRUMB: Record<Exclude<PalettePage, "root">, string> = {
  agents: "Agents",
  terminals: "Terminals",
  "new-agent": "Choose agent type",
};

/**
 * The Add Panel palette — a cmd+k-style picker for adding a panel to a section.
 * Opened from a section's "+" or the empty-section "Browse all panels" button
 * (both set `addPanelTargetZoneAtom`). Reuses the same data and actions as the
 * old "+" dropdown (`useAddPanelMenu`), but with search, keyboard navigation,
 * a changeable destination (footer pill), and drill-in sub-pages for existing
 * agents / terminals.
 */
export const AddPanelPalette = (): ReactElement => {
  const [target, setTarget] = useAtom(addPanelTargetZoneAtom);
  const close = useCallback((): void => setTarget(null), [setTarget]);

  return (
    <Dialog.Root
      open={target !== null}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      {/* No Dialog.Portal: keep the content inside the `.radix-themes` tree so
          dark-mode tokens apply (same pattern as CommandPalette). */}
      <Dialog.Overlay className={styles.overlay} />
      {target !== null && <PaletteBody initialZone={target} onClose={close} />}
    </Dialog.Root>
  );
};

const PaletteBody = ({ initialZone, onClose }: { initialZone: ZoneId; onClose: () => void }): ReactElement => {
  const [zone, setZone] = useState<ZoneId>(initialZone);
  const [page, setPage] = useState<PalettePage>("root");
  const [search, setSearch] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const menu = useAddPanelMenu(zone);
  const { registrations, refetch: refreshRegistrations } = useTerminalAgentRegistrations();
  const isPiAgentEnabled = useAtomValue(isPiAgentEnabledAtom);
  const destinations = useDestinationSections();
  const currentLabel = destinations.find((d) => d.zone === zone)?.label ?? "section";

  // Close FIRST, then perform the action: the palette must never be left
  // hanging open because an add action failed mid-way.
  const run = useCallback(
    (action: () => void): void => {
      onClose();
      action();
    },
    [onClose],
  );

  const goBack = useCallback((): void => {
    setPage("root");
    setSearch("");
  }, []);

  const openPage = useCallback((next: Exclude<PalettePage, "root">): void => {
    setPage(next);
    setSearch("");
  }, []);

  // Re-read the registrations directory before showing the harness picker so
  // it tracks the filesystem without a restart (same as the old + menu).
  const openChooseAgent = useCallback((): void => {
    refreshRegistrations();
    openPage("new-agent");
  }, [refreshRegistrations, openPage]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>): void => {
      // Backspace on an empty search inside a sub-page returns to the root page
      // — mirrors the command palette's sub-page back behavior.
      if (e.key === "Backspace" && search === "" && page !== "root") {
        e.preventDefault();
        goBack();
        return;
      }

      // ArrowRight on the "Choose agent type…" row drills into the picker — the
      // same affordance as its trailing chevron and Enter. Gated on an empty
      // search so it doesn't hijack text-cursor movement; cmdk marks the active
      // row with data-selected, and only that row's value carries "choose-agent".
      if (e.key === "ArrowRight" && page === "root" && search === "") {
        const active = document.querySelector('[cmdk-item][data-selected="true"]');
        if ((active?.getAttribute("data-value") ?? "").toLowerCase().startsWith("choose-agent")) {
          e.preventDefault();
          openChooseAgent();
        }
      }
    },
    [search, page, goBack, openChooseAgent],
  );

  const placeholder =
    page === "agents"
      ? "Filter agents…"
      : page === "terminals"
        ? "Filter terminals…"
        : page === "new-agent"
          ? "Choose an agent type…"
          : `Add a panel to the ${inSentence(currentLabel)} section…`;

  return (
    <Dialog.Content
      className={styles.content}
      aria-describedby={undefined}
      data-testid="add-panel-palette"
      // Esc inside a sub-page goes back instead of closing the palette.
      onEscapeKeyDown={(e): void => {
        if (page !== "root") {
          e.preventDefault();
          goBack();
        }
      }}
    >
      <VisuallyHidden>
        <Dialog.Title>Add panel</Dialog.Title>
      </VisuallyHidden>
      <Command label="Add panel" className={styles.command} loop onKeyDownCapture={handleKeyDown}>
        <div className={styles.header}>
          <span className={styles.searchIcon} aria-hidden>
            <Search size={18} />
          </span>
          {page !== "root" && (
            <span className={styles.breadcrumb}>
              <span className={styles.breadcrumbRoot} onClick={goBack}>
                Add panel
              </span>
              <ChevronRight size={12} />
              <span>{PAGE_BREADCRUMB[page]}</span>
              <button type="button" className={styles.breadcrumbClose} aria-label="Back" onClick={goBack}>
                <X size={10} />
              </button>
            </span>
          )}
          <Command.Input
            ref={inputRef}
            value={search}
            onValueChange={setSearch}
            placeholder={placeholder}
            className={styles.input}
            autoFocus
            data-testid="add-panel-input"
          />
        </div>
        <div className={styles.divider} aria-hidden />
        <Command.List className={styles.list} data-testid="add-panel-list">
          <Command.Empty className={styles.empty}>
            {search === "" ? "Nothing to add here." : `No matches for "${search}"`}
          </Command.Empty>

          {page === "root" && (
            <RootPage
              menu={menu}
              registrations={registrations}
              onCreateAgent={() => run(() => menu.createAgent())}
              onChooseAgent={openChooseAgent}
              onCreateTerminal={() => run(menu.createTerminal)}
              onOpenPanel={(id) => run(() => menu.openPanel(id))}
              onOpenPage={openPage}
            />
          )}
          {page === "agents" && (
            <ExistingPage panels={menu.existingAgents} onOpenPanel={(id) => run(() => menu.openPanel(id))} />
          )}
          {page === "terminals" && (
            <ExistingPage panels={menu.existingTerminals} onOpenPanel={(id) => run(() => menu.openPanel(id))} />
          )}
          {page === "new-agent" && (
            <ChooseAgentPage
              defaultAgentType={menu.defaultAgentType}
              registrations={registrations}
              isPiAgentEnabled={isPiAgentEnabled}
              onCreate={(harness, registrationId) => run(() => menu.createAgent(harness, registrationId))}
            />
          )}
        </Command.List>

        <PaletteFooter enterLabel="add" escLabel={page === "root" ? "close" : "back"}>
          <DestinationSelect
            zone={zone}
            label={currentLabel}
            destinations={destinations}
            onChange={setZone}
            inputRef={inputRef}
          />
        </PaletteFooter>
      </Command>
    </Dialog.Content>
  );
};

const RootPage = ({
  menu,
  registrations,
  onCreateAgent,
  onChooseAgent,
  onCreateTerminal,
  onOpenPanel,
  onOpenPage,
}: {
  menu: ReturnType<typeof useAddPanelMenu>;
  registrations: ReadonlyArray<AgentRegistrationLabel>;
  onCreateAgent: () => void;
  onChooseAgent: () => void;
  onCreateTerminal: () => void;
  onOpenPanel: (id: string) => void;
  onOpenPage: (page: Exclude<PalettePage, "root">) => void;
}): ReactElement => (
  <>
    <Command.Group heading="Create" className={styles.group}>
      {/* Fast path: one keystroke creates the recently-used agent type. */}
      <Row
        value="new-agent New agent recent last claude pi cli"
        icon={<MessageSquarePlus size={17} />}
        title={`New ${agentTypeDisplayLabel(menu.defaultAgentType, registrations)} agent`}
        subtitle="Reuse your last agent type"
        onSelect={onCreateAgent}
        testId={ElementIds.ADD_AGENT_BUTTON}
      />
      {/* Drill-in: pick any agent type from the "Choose agent" sub-page. */}
      <Row
        value="choose-agent New agent type harness select claude pi cli terminal"
        icon={<MessageSquarePlus size={17} />}
        title="Choose agent type…"
        subtitle="Claude, pi, or a CLI agent"
        trailing={
          <span className={styles.chevron}>
            <ChevronRight size={15} />
          </span>
        }
        onSelect={onChooseAgent}
        testId={ElementIds.ADD_AGENT_CHEVRON_BUTTON}
      />
      <Row
        value="new-terminal New terminal shell command line"
        icon={<SquareTerminal size={17} />}
        title="New terminal"
        subtitle="Start an interactive shell"
        onSelect={onCreateTerminal}
      />
    </Command.Group>

    {menu.staticPanels.length > 0 && (
      <Command.Group heading="Panels" className={styles.group}>
        {menu.staticPanels.map((panel) => (
          <PanelRow key={panel.id} panel={panel} onSelect={() => onOpenPanel(panel.id)} />
        ))}
      </Command.Group>
    )}

    {(menu.existingAgents.length > 0 || menu.existingTerminals.length > 0) && (
      <Command.Group className={styles.group}>
        {menu.existingAgents.length > 0 && (
          <Row
            value="open-existing-agent agent move reopen restore"
            icon={<MessageSquarePlus size={17} />}
            title="Open existing agent"
            subtitle="Move an existing agent into this section"
            trailing={<DrillInTrailing count={menu.existingAgents.length} />}
            onSelect={() => onOpenPage("agents")}
          />
        )}
        {menu.existingTerminals.length > 0 && (
          <Row
            value="open-existing-terminal terminal move reopen restore"
            icon={<SquareTerminal size={17} />}
            title="Open existing terminal"
            subtitle="Move an existing terminal into this section"
            trailing={<DrillInTrailing count={menu.existingTerminals.length} />}
            onSelect={() => onOpenPage("terminals")}
          />
        )}
      </Command.Group>
    )}
  </>
);

const DrillInTrailing = ({ count }: { count: number }): ReactElement => (
  <>
    <span className={styles.count}>{count}</span>
    <span className={styles.chevron}>
      <ChevronRight size={15} />
    </span>
  </>
);

const ExistingPage = ({
  panels,
  onOpenPanel,
}: {
  panels: ReadonlyArray<PanelDefinition>;
  onOpenPanel: (id: string) => void;
}): ReactElement => (
  <>
    {panels.map((panel) => (
      <PanelRow key={panel.id} panel={panel} onSelect={() => onOpenPanel(panel.id)} />
    ))}
  </>
);

const PanelRow = ({ panel, onSelect }: { panel: PanelDefinition; onSelect: () => void }): ReactElement => {
  const Icon = panel.icon;
  return (
    <Row
      value={`${panel.id} ${panel.displayName} ${panel.description}`}
      icon={panel.tabIcon ?? <Icon size={17} />}
      title={panel.displayName}
      subtitle={panel.description}
      onSelect={onSelect}
    />
  );
};

const Row = ({
  value,
  icon,
  title,
  badge,
  subtitle,
  trailing,
  onSelect,
  testId,
  dataRegistrationId,
}: {
  value: string;
  icon: ReactNode;
  title: string;
  /** Inline tag rendered right after the title (e.g. a "Recently used" pill). */
  badge?: ReactNode;
  subtitle?: string;
  trailing?: ReactNode;
  onSelect: () => void;
  testId?: string;
  dataRegistrationId?: string;
}): ReactElement => (
  <Command.Item
    value={value}
    onSelect={onSelect}
    className={styles.item}
    data-testid={testId}
    data-registration-id={dataRegistrationId}
  >
    <span className={styles.itemIcon}>{icon}</span>
    <span className={styles.itemBody}>
      <span className={styles.itemTitle}>{title}</span>
      {badge}
      {subtitle != null && <span className={styles.itemSubtitle}>{subtitle}</span>}
    </span>
    {trailing != null && <span className={styles.itemTrailing}>{trailing}</span>}
  </Command.Item>
);

/**
 * The "Choose agent" sub-page: pick the harness for a new agent. Lists Claude,
 * pi (gated behind pi-agent), and each registered terminal agent (e.g. the
 * bundled Claude Code CLI) by its display name. The bare login-shell terminal
 * agent is intentionally absent — the root "New terminal" row covers raw
 * shells. The recently-used type is ordered first and tagged.
 */
const ChooseAgentPage = ({
  defaultAgentType,
  registrations,
  isPiAgentEnabled,
  onCreate,
}: {
  defaultAgentType: StoredAgentType;
  registrations: ReadonlyArray<AgentRegistrationLabel>;
  isPiAgentEnabled: boolean;
  onCreate: (harness: AgentTypeName, registrationId?: string) => void;
}): ReactElement => {
  type AgentOption = {
    key: string;
    stored: StoredAgentType;
    harness: AgentTypeName;
    registrationId?: string;
    label: string;
    icon: ReactNode;
    testId: string;
  };

  const options: Array<AgentOption> = [
    {
      key: "claude",
      stored: "claude",
      harness: "claude",
      label: AGENT_TYPE_LABELS.claude,
      icon: <MessageSquarePlus size={17} />,
      testId: ElementIds.AGENT_TYPE_MENU_ITEM_CLAUDE,
    },
  ];
  if (isPiAgentEnabled) {
    options.push({
      key: "pi",
      stored: "pi",
      harness: "pi",
      label: AGENT_TYPE_LABELS.pi,
      icon: <MessageSquarePlus size={17} />,
      testId: ElementIds.AGENT_TYPE_MENU_ITEM_PI,
    });
  }

  for (const r of registrations) {
    options.push({
      key: `registered:${r.registrationId}`,
      stored: encodeRegisteredAgentType(r.registrationId),
      harness: "registered",
      registrationId: r.registrationId,
      label: r.displayName,
      icon: <SquareTerminal size={17} />,
      testId: ElementIds.AGENT_TYPE_MENU_ITEM_REGISTERED,
    });
  }

  // Recently-used first, tagged with a pill.
  const ordered = [
    ...options.filter((o) => o.stored === defaultAgentType),
    ...options.filter((o) => o.stored !== defaultAgentType),
  ];

  return (
    <Command.Group className={styles.group} data-testid={ElementIds.AGENT_TYPE_MENU}>
      {ordered.map((opt) => (
        <Row
          key={opt.key}
          value={`agent-type ${opt.key} ${opt.label}`}
          icon={opt.icon}
          title={opt.label}
          badge={opt.stored === defaultAgentType ? <span className={styles.pill}>Recently used</span> : undefined}
          onSelect={() => onCreate(opt.harness, opt.registrationId)}
          testId={opt.testId}
          dataRegistrationId={opt.registrationId}
        />
      ))}
    </Command.Group>
  );
};

const DestinationSelect = ({
  zone,
  label,
  destinations,
  onChange,
  inputRef,
}: {
  zone: ZoneId;
  label: string;
  destinations: ReturnType<typeof useDestinationSections>;
  onChange: (zone: ZoneId) => void;
  inputRef: RefObject<HTMLInputElement | null>;
}): ReactElement => (
  <Select.Root size="1" value={zone} onValueChange={(value) => onChange(value as ZoneId)}>
    <Select.Trigger variant="ghost" color="gray" data-testid="add-panel-destination">
      Add panel to {inSentence(label)}
    </Select.Trigger>
    {/* Lift above the palette dialog (z-modal + 1): the select portals to
        <body> with no z-index of its own, same as palette tooltips. */}
    <Select.Content
      position="popper"
      side="top"
      className={styles.destinationMenu}
      // On close, Radix would re-focus the select trigger — which then eats
      // ArrowUp/Down (that's how a closed select behaves), killing the
      // palette's keyboard navigation. Send focus back to the search input.
      onCloseAutoFocus={(e): void => {
        e.preventDefault();
        inputRef.current?.focus();
      }}
    >
      {destinations.map((dest) => (
        <Select.Item key={dest.zone} value={dest.zone}>
          {dest.label}
        </Select.Item>
      ))}
    </Select.Content>
  </Select.Root>
);
