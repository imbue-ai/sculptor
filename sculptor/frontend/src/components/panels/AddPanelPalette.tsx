import * as Dialog from "@radix-ui/react-dialog";
import { Select, VisuallyHidden } from "@radix-ui/themes";
import { Command } from "cmdk";
import { useAtom } from "jotai";
import { ChevronRight, MessageSquarePlus, Search, SquareTerminal, X } from "lucide-react";
import type { KeyboardEvent, ReactElement, ReactNode, RefObject } from "react";
import { useCallback, useRef, useState } from "react";

import { PaletteFooter } from "~/components/CommandPalette/PaletteFooter.tsx";
import { addPanelTargetZoneAtom } from "~/components/panels/addPanelAtoms.ts";
import { inSentence, useDestinationSections } from "~/components/panels/destinations.ts";
import type { PanelDefinition, ZoneId } from "~/components/panels/types.ts";
import { useAddPanelMenu } from "~/pages/workspace/panels/useAddPanelMenu.ts";

import styles from "./AddPanelPalette.module.scss";

type PalettePage = "root" | "agents" | "terminals";

const PAGE_BREADCRUMB: Record<Exclude<PalettePage, "root">, string> = {
  agents: "Agents",
  terminals: "Terminals",
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

  // Backspace on an empty search inside a sub-page returns to the root page —
  // mirrors the command palette's sub-page back behavior.
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>): void => {
      if (e.key === "Backspace" && search === "" && page !== "root") {
        e.preventDefault();
        goBack();
      }
    },
    [search, page, goBack],
  );

  const placeholder =
    page === "agents"
      ? "Filter agents…"
      : page === "terminals"
        ? "Filter terminals…"
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
              onCreateAgent={() => run(menu.createAgent)}
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
  onCreateAgent,
  onCreateTerminal,
  onOpenPanel,
  onOpenPage,
}: {
  menu: ReturnType<typeof useAddPanelMenu>;
  onCreateAgent: () => void;
  onCreateTerminal: () => void;
  onOpenPanel: (id: string) => void;
  onOpenPage: (page: Exclude<PalettePage, "root">) => void;
}): ReactElement => (
  <>
    <Command.Group heading="Create" className={styles.group}>
      <Row
        value="new-agent New agent side chat conversation"
        icon={<MessageSquarePlus size={17} />}
        title="New agent"
        subtitle="Start a side conversation"
        onSelect={onCreateAgent}
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
  subtitle,
  trailing,
  onSelect,
}: {
  value: string;
  icon: ReactNode;
  title: string;
  subtitle?: string;
  trailing?: ReactNode;
  onSelect: () => void;
}): ReactElement => (
  <Command.Item value={value} onSelect={onSelect} className={styles.item}>
    <span className={styles.itemIcon}>{icon}</span>
    <span className={styles.itemBody}>
      <span className={styles.itemTitle}>{title}</span>
      {subtitle != null && <span className={styles.itemSubtitle}>{subtitle}</span>}
    </span>
    {trailing != null && <span className={styles.itemTrailing}>{trailing}</span>}
  </Command.Item>
);

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
