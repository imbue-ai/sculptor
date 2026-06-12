import * as ToastPrimitive from "@radix-ui/react-toast";
import {
  AlertDialog,
  Avatar,
  Badge,
  Box,
  Button,
  Callout,
  Card,
  Checkbox,
  CheckboxCards,
  CheckboxGroup,
  Code as RadixCode,
  ContextMenu,
  DataList,
  Dialog,
  DropdownMenu,
  Flex,
  Heading,
  HoverCard,
  IconButton,
  Kbd,
  Link,
  Popover,
  Progress,
  Quote,
  RadioCards,
  RadioGroup,
  ScrollArea,
  SegmentedControl,
  Select,
  Separator,
  Skeleton,
  Slider,
  Spinner,
  Strong,
  Switch,
  Table,
  Tabs,
  Text,
  TextArea,
  TextField,
  Theme,
  Tooltip,
} from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Provider as JotaiProvider } from "jotai/react";
import {
  Activity,
  AlertTriangle,
  Bell,
  Clipboard,
  Copy,
  Edit3,
  FileText,
  GitBranch,
  Home,
  Info,
  Moon,
  Pencil,
  Plus,
  Save,
  Search,
  Settings,
  Sun,
  Terminal,
  Trash2,
  X,
} from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { Component, useCallback, useEffect, useRef, useState } from "react";

import type { AskUserQuestionData, CustomAction } from "~/api";
import type {
  AccentColor,
  FontOption,
  GrayColor,
  HexOverrides,
  PanelBackground,
  Radius,
  Scaling,
} from "~/common/state/atoms/themeBuilder.ts";
import {
  ACCENT_COLORS,
  DEFAULT_HEX_OVERRIDES,
  DEFAULT_THEME_BUILDER_SETTINGS,
  GRAY_COLORS,
  PANEL_BACKGROUNDS,
  RADII,
  SCALINGS,
  themeBuilderSettingsAtom,
} from "~/common/state/atoms/themeBuilder.ts";
import type { ShikiThemePairName } from "~/common/theme/shikiThemes.ts";
import { ActionChip } from "~/components/actions/ActionChip";
import { ActionDialog } from "~/components/actions/ActionDialog";
import { BranchSelectorCore } from "~/components/BranchSelectorCore";
import { Code } from "~/components/Code";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog";
import { ImageLightbox } from "~/components/ImageLightbox";
import { InlineRenameInput } from "~/components/InlineRenameInput";
import { MarkdownBlock } from "~/components/MarkdownBlock";
import { BlandCircle, PulsingCircle } from "~/components/PulsingCircle";
import { TabBar } from "~/components/tabs/TabBar";
import type { TabDefinition } from "~/components/tabs/types";
import { Toast, ToastType } from "~/components/Toast";
import { TooltipIconButton } from "~/components/TooltipIconButton";
import { WarningStatusBanner } from "~/components/WarningStatusBanner";
import { AskUserQuestion } from "~/pages/workspace/components/AskUserQuestion";

import styles from "./ComponentGalleryPage.module.scss";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_BRANCHES = [
  { branch: "main", badges: [] },
  { branch: "feature/auth-flow", badges: [] },
  { branch: "fix/login-bug", badges: [] },
  { branch: "dev/refactor-sidebar", badges: [] },
  { branch: "release/v2.0", badges: [] },
];

const MOCK_MARKDOWN = `# Heading 1
## Heading 2
### Heading 3

Regular text with **bold**, *italic*, and \`inline code\`.

- Bullet list item 1
- Bullet list item 2
  - Nested item

1. Ordered item
2. Another item

> This is a blockquote

\`\`\`typescript
const hello = (name: string): string => {
  return \`Hello, \${name}!\`;
};
\`\`\`

| Column A | Column B |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |

A [link](https://example.com) and an emoji :rocket:`;

const MOCK_ACTIONS: ReadonlyArray<CustomAction> = [
  { id: "1", name: "Review PR", prompt: "Review this pull request for issues", autoSubmit: true, groupId: null },
  { id: "2", name: "Write Tests", prompt: "Write unit tests for the selected code", autoSubmit: true, groupId: null },
  {
    id: "3",
    name: "Draft Message",
    prompt: "Draft a commit message for these changes",
    autoSubmit: false,
    groupId: null,
  },
  { id: "4", name: "Explain Code", prompt: "Explain how this code works", autoSubmit: true, groupId: null },
];

const MOCK_TABS: ReadonlyArray<TabDefinition> = [
  { id: "tab-1", label: "Home", icon: <Home width={14} height={14} /> },
  { id: "tab-2", label: "Settings", icon: <Settings width={14} height={14} /> },
  { id: "tab-3", label: "Documents", icon: <FileText width={14} height={14} /> },
  { id: "tab-4", label: "Terminal", icon: <Terminal width={14} height={14} /> },
  { id: "tab-5", label: "Activity", icon: <Activity width={14} height={14} /> },
];

const MOCK_QUESTION_DATA: AskUserQuestionData = {
  questions: [
    {
      question: "Where should the workspace panel live in the layout?",
      header: "LAYOUT",
      options: [
        { label: "New DockingLayout panel", description: "Add it as a panel in the existing docking system" },
        { label: "Fixed left sidebar", description: "A dedicated section outside the DockingLayout" },
        { label: "Toggleable sidebar", description: "A fixed sidebar that can be toggled on/off" },
      ],
      multiSelect: false,
    },
  ],
  toolUseId: "gallery-tool-1",
};

const MOCK_MULTI_QUESTION_DATA: AskUserQuestionData = {
  questions: [
    {
      question: "Which database should we use?",
      header: "DATABASE",
      options: [
        { label: "PostgreSQL", description: "Relational with strong ACID compliance" },
        { label: "MongoDB", description: "Document-oriented NoSQL" },
        { label: "SQLite", description: "Lightweight embedded database" },
      ],
      multiSelect: false,
    },
    {
      question: "Which features do you want to enable?",
      header: "FEATURES",
      options: [
        { label: "Real-time updates", description: "WebSocket-based live data" },
        { label: "Dark mode", description: "Light and dark theme variants" },
        { label: "Export to CSV", description: "Download data as CSV files" },
      ],
      multiSelect: true,
    },
  ],
  toolUseId: "gallery-tool-2",
};

// ---------------------------------------------------------------------------
// Navigation sections
// ---------------------------------------------------------------------------

const SECTIONS = [
  { id: "radix-primitives", label: "Radix Primitives" },
  { id: "status-indicators", label: "Status & Indicators" },
  { id: "inputs-editing", label: "Inputs & Editing" },
  { id: "navigation-selection", label: "Navigation & Selection" },
  { id: "content-display", label: "Content Display" },
  { id: "dialogs-modals", label: "Dialogs & Modals" },
  { id: "cards-banners", label: "Cards & Banners" },
] as const;

// ---------------------------------------------------------------------------
// Section component
// ---------------------------------------------------------------------------

const Section = ({ id, title, children }: { id: string; title: string; children: ReactNode }): ReactElement => (
  <section id={id} className={styles.section}>
    <h2 className={styles.sectionTitle}>{title}</h2>
    {children}
  </section>
);

const ComponentBlock = ({
  id,
  name,
  description,
  children,
}: {
  id?: string;
  name: string;
  description: string;
  children: ReactNode;
}): ReactElement => (
  <div id={id} className={styles.componentBlock}>
    <h3 className={styles.componentName}>{name}</h3>
    <p className={styles.componentDescription}>{description}</p>
    <div className={styles.componentPreview}>
      <ComponentErrorBoundary name={name}>{children}</ComponentErrorBoundary>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Interactive demos
// ---------------------------------------------------------------------------

const TabBarDemo = (): ReactElement => {
  const [openTabIds, setOpenTabIds] = useState<Array<string>>(["tab-1", "tab-2", "tab-3"]);
  const [activeTabId, setActiveTabId] = useState<string>("tab-1");
  const tabHistoryRef = useRef<Array<string>>(["tab-1"]);

  const handleActivate = useCallback((tabId: string): void => {
    tabHistoryRef.current = [...tabHistoryRef.current, tabId];
    setActiveTabId(tabId);
  }, []);

  const handleClose = useCallback(
    (tabId: string): void => {
      const nextOpenTabIds = openTabIds.filter((id) => id !== tabId);
      if (nextOpenTabIds.length === 0) return;
      setOpenTabIds(nextOpenTabIds);
      if (tabId === activeTabId) {
        const history = tabHistoryRef.current.filter((id) => id !== tabId && nextOpenTabIds.includes(id));
        setActiveTabId(history.length > 0 ? history[history.length - 1] : nextOpenTabIds[0]);
      }
      tabHistoryRef.current = tabHistoryRef.current.filter((id) => id !== tabId);
    },
    [openTabIds, activeTabId],
  );

  const handleReorder = useCallback((newOrder: Array<string>): void => {
    setOpenTabIds(newOrder);
  }, []);

  return (
    <div style={{ width: "100%", border: "1px solid var(--gray-a5)" }}>
      <TabBar
        tabs={[...MOCK_TABS]}
        openTabIds={openTabIds}
        activeTabId={activeTabId}
        onActivate={handleActivate}
        onClose={handleClose}
        onReorder={handleReorder}
      />
    </div>
  );
};

const CompactTabBarDemo = (): ReactElement => {
  const allIds = MOCK_TABS.map((t) => t.id);
  const [openTabIds, setOpenTabIds] = useState<Array<string>>(allIds);
  const [activeTabId, setActiveTabId] = useState<string>(allIds[0]);
  const tabHistoryRef = useRef<Array<string>>([allIds[0]]);

  const handleActivate = useCallback((tabId: string): void => {
    tabHistoryRef.current = [...tabHistoryRef.current, tabId];
    setActiveTabId(tabId);
  }, []);

  const handleClose = useCallback(
    (tabId: string): void => {
      const nextOpenTabIds = openTabIds.filter((id) => id !== tabId);
      if (nextOpenTabIds.length === 0) return;
      setOpenTabIds(nextOpenTabIds);
      if (tabId === activeTabId) {
        const history = tabHistoryRef.current.filter((id) => id !== tabId && nextOpenTabIds.includes(id));
        setActiveTabId(history.length > 0 ? history[history.length - 1] : nextOpenTabIds[0]);
      }
      tabHistoryRef.current = tabHistoryRef.current.filter((id) => id !== tabId);
    },
    [openTabIds, activeTabId],
  );

  const handleReorder = useCallback((newOrder: Array<string>): void => {
    setOpenTabIds(newOrder);
  }, []);

  return (
    <div style={{ width: "100%", border: "1px solid var(--gray-a5)" }}>
      <TabBar
        tabs={[...MOCK_TABS]}
        openTabIds={openTabIds}
        activeTabId={activeTabId}
        onActivate={handleActivate}
        onClose={handleClose}
        onReorder={handleReorder}
        variant="compact"
        alwaysCloseable
      />
    </div>
  );
};

const InlineRenameDemo = (): ReactElement => {
  const [isEditing, setIsEditing] = useState(false);
  const [value, setValue] = useState("Double-click to rename");

  return (
    <Flex align="center" gap="2">
      {isEditing ? (
        <InlineRenameInput
          value={value}
          isEditing={isEditing}
          onCommit={(newValue) => {
            setValue(newValue);
            setIsEditing(false);
          }}
          onCancel={() => setIsEditing(false)}
        />
      ) : (
        <Text size="2" onDoubleClick={() => setIsEditing(true)} style={{ cursor: "pointer" }}>
          {value}
        </Text>
      )}
      <IconButton variant="ghost" size="1" onClick={() => setIsEditing(true)}>
        <Pencil size={14} />
      </IconButton>
    </Flex>
  );
};

const ToastDemo = ({
  dangerColor,
  infoColor,
  successColor,
  warningColor,
}: {
  dangerColor: AccentColor;
  infoColor: AccentColor;
  successColor: AccentColor;
  warningColor: AccentColor;
}): ReactElement => {
  const [openToast, setOpenToast] = useState<string | null>(null);

  return (
    <ToastPrimitive.Provider swipeDirection="right">
      <Flex gap="2" wrap="wrap">
        <Button size="1" variant="soft" onClick={() => setOpenToast("default")}>
          Default Toast
        </Button>
        <Button size="1" variant="soft" color={successColor} onClick={() => setOpenToast("success")}>
          Success Toast
        </Button>
        <Button size="1" variant="soft" color={dangerColor} onClick={() => setOpenToast("error")}>
          Error Toast
        </Button>
        <Button size="1" variant="soft" color={warningColor} onClick={() => setOpenToast("warning")}>
          Warning Toast
        </Button>
        <Button size="1" variant="soft" color={dangerColor} onClick={() => setOpenToast("errorProminent")}>
          Error Prominent Toast
        </Button>
        <Button size="1" variant="soft" color={infoColor} onClick={() => setOpenToast("action")}>
          Toast with Action
        </Button>
      </Flex>
      <Toast
        open={openToast === "default"}
        onOpenChange={(open) => !open && setOpenToast(null)}
        title="Default notification"
        description="Something happened."
        type={ToastType.DEFAULT}
      />
      <Toast
        open={openToast === "success"}
        onOpenChange={(open) => !open && setOpenToast(null)}
        title="Success!"
        description="Operation completed."
        type={ToastType.SUCCESS}
      />
      <Toast
        open={openToast === "error"}
        onOpenChange={(open) => !open && setOpenToast(null)}
        title="Error"
        description="Something went wrong."
        type={ToastType.ERROR}
      />
      <Toast
        open={openToast === "warning"}
        onOpenChange={(open) => !open && setOpenToast(null)}
        title="Warning"
        description="Proceed with caution."
        type={ToastType.WARNING}
      />
      <Toast
        open={openToast === "errorProminent"}
        onOpenChange={(open) => !open && setOpenToast(null)}
        title="Critical Error"
        description="A critical error has occurred."
        type={ToastType.ERROR_PROMINENT}
      />
      <Toast
        open={openToast === "action"}
        onOpenChange={(open) => !open && setOpenToast(null)}
        title="File saved"
        description="Your changes have been saved."
        type={ToastType.SUCCESS}
        action={{ label: "Undo", handleClick: () => setOpenToast(null) }}
      />
      <ToastPrimitive.Viewport style={{ position: "fixed", bottom: 16, right: 16, zIndex: 4000, maxWidth: 400 }} />
    </ToastPrimitive.Provider>
  );
};

const ImageLightboxDemo = (): ReactElement => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <Button size="1" variant="soft" onClick={() => setIsOpen(true)}>
        Open Lightbox (placeholder image)
      </Button>
      {isOpen && (
        <ImageLightbox
          media={[
            {
              url: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='300'%3E%3Crect width='400' height='300' fill='%23e8e0d4'/%3E%3Ctext x='200' y='150' text-anchor='middle' fill='%23857c6e' font-size='24'%3EPlaceholder%3C/text%3E%3C/svg%3E",
              isVideo: false,
              name: "placeholder.svg",
            },
          ]}
          initialIndex={0}
          onClose={() => setIsOpen(false)}
        />
      )}
    </>
  );
};

const DeleteDialogDemo = ({ dangerColor }: { dangerColor: AccentColor }): ReactElement => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <Button size="1" variant="soft" color={dangerColor} onClick={() => setIsOpen(true)}>
        Open Delete Dialog
      </Button>
      <DeleteConfirmationDialog
        isOpen={isOpen}
        onOpenChange={setIsOpen}
        entityType="workspace"
        entityName="my-workspace"
        onConfirm={() => setIsOpen(false)}
      />
    </>
  );
};

const ActionDialogDemo = (): ReactElement => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <Button size="1" variant="soft" onClick={() => setIsOpen(true)}>
        Open Action Dialog
      </Button>
      <ActionDialog open={isOpen} onOpenChange={setIsOpen} groups={[]} onSave={() => setIsOpen(false)} />
    </>
  );
};

// ---------------------------------------------------------------------------
// Error boundary for isolating component failures
// ---------------------------------------------------------------------------

type ErrorBoundaryState = {
  error: Error | null;
};

class ComponentErrorBoundary extends Component<{ children: ReactNode; name: string }, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override render(): ReactNode {
    if (this.state.error) {
      return (
        <Box
          style={{
            background: "var(--red-a2)",
            border: "1px solid var(--red-a5)",
            borderRadius: "var(--radius-3)",
            padding: "var(--space-3)",
          }}
        >
          <Text size="2" color="red" weight="bold">
            {this.props.name} failed to render
          </Text>
          <Text as="p" size="1" color="red" style={{ marginTop: "var(--space-1)" }}>
            {this.state.error.message}
          </Text>
        </Box>
      );
    }
    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// Theme settings for the gallery page (differs from app-wide ThemeBuilderSettings
// by restricting appearance to "light" | "dark" without "system")
// ---------------------------------------------------------------------------

type ThemeSettings = {
  accentColor: AccentColor;
  appearance: "light" | "dark";
  codeFont: FontOption;
  codeTheme: ShikiThemePairName;
  dangerColor: AccentColor;
  grayColor: GrayColor;
  hexOverrides: HexOverrides;
  infoColor: AccentColor;
  panelBackground: PanelBackground;
  primaryFont: FontOption;
  radius: Radius;
  scaling: Scaling;
  successColor: AccentColor;
  warningColor: AccentColor;
};

// ---------------------------------------------------------------------------
// Theme controls toolbar
// ---------------------------------------------------------------------------

const ThemeControlSelect = <T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: ReadonlyArray<T>;
  onChange: (value: T) => void;
}): ReactElement => (
  <Flex direction="column" gap="1">
    <Text size="1" color="gray" weight="medium">
      {label}
    </Text>
    <Select.Root size="1" value={value} onValueChange={(v) => onChange(v as T)}>
      <Select.Trigger variant="surface" />
      <Select.Content position="popper" sideOffset={4}>
        {options.map((option) => (
          <Select.Item key={option} value={option}>
            {option}
          </Select.Item>
        ))}
      </Select.Content>
    </Select.Root>
  </Flex>
);

const ThemeControls = ({
  settings,
  onSettingsChange,
  onSave,
}: {
  settings: ThemeSettings;
  onSettingsChange: (patch: Partial<ThemeSettings>) => void;
  onSave: () => void;
}): ReactElement => (
  <div className={styles.controlsBar}>
    <Flex align="center" gap="4" wrap="wrap">
      <Text size="2" weight="bold" style={{ marginRight: "var(--space-2)" }}>
        Theme
      </Text>

      <ThemeControlSelect
        label="Accent"
        value={settings.accentColor}
        options={ACCENT_COLORS}
        onChange={(accentColor) => onSettingsChange({ accentColor })}
      />

      <ThemeControlSelect
        label="Gray"
        value={settings.grayColor}
        options={GRAY_COLORS}
        onChange={(grayColor) => onSettingsChange({ grayColor })}
      />

      <ThemeControlSelect
        label="Radius"
        value={settings.radius}
        options={RADII}
        onChange={(radius) => onSettingsChange({ radius })}
      />

      <ThemeControlSelect
        label="Scaling"
        value={settings.scaling}
        options={SCALINGS}
        onChange={(scaling) => onSettingsChange({ scaling })}
      />

      <ThemeControlSelect
        label="Panel"
        value={settings.panelBackground}
        options={PANEL_BACKGROUNDS}
        onChange={(panelBackground) => onSettingsChange({ panelBackground })}
      />

      <Flex direction="column" gap="1">
        <Text size="1" color="gray" weight="medium">
          Mode
        </Text>
        <IconButton
          variant="soft"
          size="1"
          onClick={() => onSettingsChange({ appearance: settings.appearance === "light" ? "dark" : "light" })}
        >
          {settings.appearance === "light" ? <Moon size={14} /> : <Sun size={14} />}
        </IconButton>
      </Flex>

      <Separator orientation="vertical" size="2" />

      <ThemeControlSelect
        label="Danger"
        value={settings.dangerColor}
        options={ACCENT_COLORS}
        onChange={(dangerColor) => onSettingsChange({ dangerColor })}
      />

      <ThemeControlSelect
        label="Success"
        value={settings.successColor}
        options={ACCENT_COLORS}
        onChange={(successColor) => onSettingsChange({ successColor })}
      />

      <ThemeControlSelect
        label="Warning"
        value={settings.warningColor}
        options={ACCENT_COLORS}
        onChange={(warningColor) => onSettingsChange({ warningColor })}
      />

      <ThemeControlSelect
        label="Info"
        value={settings.infoColor}
        options={ACCENT_COLORS}
        onChange={(infoColor) => onSettingsChange({ infoColor })}
      />

      <Separator orientation="vertical" size="2" />

      <Button
        variant="ghost"
        size="1"
        onClick={() =>
          onSettingsChange({
            ...DEFAULT_THEME_BUILDER_SETTINGS,
            appearance:
              DEFAULT_THEME_BUILDER_SETTINGS.appearance === "system"
                ? "light"
                : DEFAULT_THEME_BUILDER_SETTINGS.appearance,
          })
        }
      >
        Reset to defaults
      </Button>
      <Button variant="soft" size="1" onClick={onSave}>
        <Save size={14} />
        Save to theme
      </Button>
    </Flex>
  </div>
);

// ---------------------------------------------------------------------------
// Main gallery page
// ---------------------------------------------------------------------------

const GalleryContent = ({
  settings,
  onSettingsChange,
  onSave,
}: {
  settings: ThemeSettings;
  onSettingsChange: (patch: Partial<ThemeSettings>) => void;
  onSave: () => void;
}): ReactElement => {
  const [activeSectionId, setActiveSectionId] = useState<string>(SECTIONS[0].id);

  useEffect(() => {
    const sectionElements = SECTIONS.map((s) => document.getElementById(s.id)).filter(
      (el): el is HTMLElement => el !== null,
    );
    if (sectionElements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        // Find the topmost visible section
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) {
          setActiveSectionId(visible[0].target.id);
        }
      },
      { rootMargin: "-10% 0px -70% 0px", threshold: 0 },
    );

    for (const el of sectionElements) {
      observer.observe(el);
    }
    return (): void => observer.disconnect();
  }, []);

  return (
    <Theme
      accentColor={settings.accentColor}
      grayColor={settings.grayColor}
      appearance={settings.appearance}
      radius={settings.radius}
      scaling={settings.scaling}
      panelBackground={settings.panelBackground}
      style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}
    >
      <JotaiProvider>
        <div className={styles.galleryWrapper}>
          <ThemeControls settings={settings} onSettingsChange={onSettingsChange} onSave={onSave} />

          <div className={styles.page}>
            {/* Sidebar navigation */}
            <nav className={styles.sidebar}>
              <div className={styles.sidebarTitle}>Components</div>
              {SECTIONS.map((section) => (
                <div key={section.id} className={styles.navGroup}>
                  <a
                    href={`#${section.id}`}
                    className={`${styles.navLink} ${activeSectionId === section.id ? styles.active : ""}`}
                    onClick={(e) => {
                      e.preventDefault();
                      document.getElementById(section.id)?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    {section.label}
                  </a>
                </div>
              ))}
            </nav>

            {/* Main content */}
            <main className={styles.main}>
              <header className={styles.header}>
                <h1 className={styles.headerTitle}>Component Gallery</h1>
                <p className={styles.headerDescription}>
                  Visual reference of every UI component in Sculptor. Internal debug page.
                </p>
              </header>

              {/* ============================================================
                SECTION: Radix Primitives
                ============================================================ */}
              <Section id="radix-primitives" title="Radix Primitives">
                <ComponentBlock
                  name="Button"
                  description="Primary action button. Used throughout the app for form submissions, confirmations, and CTAs."
                >
                  <Flex direction="column" gap="3">
                    <div className={styles.variantLabel}>Variants</div>
                    <div className={styles.variantRow}>
                      <Button variant="classic">Classic</Button>
                      <Button variant="solid">Solid</Button>
                      <Button variant="soft">Soft</Button>
                      <Button variant="surface">Surface</Button>
                      <Button variant="outline">Outline</Button>
                      <Button variant="ghost">Ghost</Button>
                    </div>
                    <div className={styles.variantLabel}>Sizes</div>
                    <div className={styles.variantRow}>
                      <Button size="1">Size 1</Button>
                      <Button size="2">Size 2</Button>
                      <Button size="3">Size 3</Button>
                      <Button size="4">Size 4</Button>
                    </div>
                    <div className={styles.variantLabel}>Colors</div>
                    <div className={styles.variantRow}>
                      <Button>Accent (theme)</Button>
                      <Button color="gray">Gray</Button>
                      <Button color={settings.dangerColor}>Danger</Button>
                      <Button color={settings.infoColor}>Info</Button>
                      <Button color={settings.successColor}>Success</Button>
                      <Button color={settings.warningColor}>Warning</Button>
                    </div>
                    <div className={styles.variantLabel}>States</div>
                    <div className={styles.variantRow}>
                      <Button disabled>Disabled</Button>
                      <Button loading>Loading</Button>
                    </div>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="IconButton"
                  description="Compact button showing only an icon. Used in toolbars, tab bars, and inline controls."
                >
                  <div className={styles.variantRow}>
                    <IconButton variant="solid">
                      <Plus size={16} />
                    </IconButton>
                    <IconButton variant="soft">
                      <Settings size={16} />
                    </IconButton>
                    <IconButton variant="surface">
                      <Search size={16} />
                    </IconButton>
                    <IconButton variant="outline">
                      <Edit3 size={16} />
                    </IconButton>
                    <IconButton variant="ghost">
                      <X size={16} />
                    </IconButton>
                    <IconButton variant="ghost" color={settings.dangerColor}>
                      <Trash2 size={16} />
                    </IconButton>
                  </div>
                </ComponentBlock>

                <ComponentBlock
                  name="TextField"
                  description="Single-line text input. Used in forms, search bars, and rename inputs."
                >
                  <Flex direction="column" gap="3" style={{ maxWidth: 400 }}>
                    <TextField.Root placeholder="Default input" />
                    <TextField.Root placeholder="With icon" size="2">
                      <TextField.Slot>
                        <Search size={14} />
                      </TextField.Slot>
                    </TextField.Root>
                    <TextField.Root placeholder="Disabled" disabled />
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="TextArea"
                  description="Multi-line text input. Used in action dialogs, editors, and prompts."
                >
                  <Flex direction="column" gap="3" style={{ maxWidth: 400 }}>
                    <TextArea placeholder="Type something here..." />
                    <TextArea placeholder="Disabled" disabled />
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="Select"
                  description="Dropdown selector. Used for model selection, branch selection, and settings."
                >
                  <Flex gap="3">
                    <Select.Root defaultValue="option1">
                      <Select.Trigger placeholder="Select option..." />
                      <Select.Content>
                        <Select.Item value="option1">Option 1</Select.Item>
                        <Select.Item value="option2">Option 2</Select.Item>
                        <Select.Item value="option3">Option 3</Select.Item>
                      </Select.Content>
                    </Select.Root>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="Checkbox, Switch, RadioGroup"
                  description="Toggle and selection inputs. Used in settings, multi-select questions, and filters."
                >
                  <Flex gap="6" align="start">
                    <Flex direction="column" gap="2">
                      <div className={styles.variantLabel}>Checkbox</div>
                      <Text as="label" size="2">
                        <Flex gap="2" align="center">
                          <Checkbox defaultChecked /> Checked
                        </Flex>
                      </Text>
                      <Text as="label" size="2">
                        <Flex gap="2" align="center">
                          <Checkbox /> Unchecked
                        </Flex>
                      </Text>
                      <Text as="label" size="2">
                        <Flex gap="2" align="center">
                          <Checkbox disabled /> Disabled
                        </Flex>
                      </Text>
                    </Flex>
                    <Flex direction="column" gap="2">
                      <div className={styles.variantLabel}>Switch</div>
                      <Text as="label" size="2">
                        <Flex gap="2" align="center">
                          <Switch defaultChecked /> Enabled
                        </Flex>
                      </Text>
                      <Text as="label" size="2">
                        <Flex gap="2" align="center">
                          <Switch /> Disabled
                        </Flex>
                      </Text>
                    </Flex>
                    <Flex direction="column" gap="2">
                      <div className={styles.variantLabel}>Radio Group</div>
                      <RadioGroup.Root defaultValue="a">
                        <RadioGroup.Item value="a">Option A</RadioGroup.Item>
                        <RadioGroup.Item value="b">Option B</RadioGroup.Item>
                        <RadioGroup.Item value="c">Option C</RadioGroup.Item>
                      </RadioGroup.Root>
                    </Flex>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="CheckboxGroup, CheckboxCards, RadioCards"
                  description="Card-based selection inputs. Provide rich selection UI with descriptions."
                >
                  <Flex direction="column" gap="4">
                    <Flex direction="column" gap="2">
                      <div className={styles.variantLabel}>Checkbox Group</div>
                      <CheckboxGroup.Root defaultValue={["a"]}>
                        <CheckboxGroup.Item value="a">Enable notifications</CheckboxGroup.Item>
                        <CheckboxGroup.Item value="b">Auto-save changes</CheckboxGroup.Item>
                        <CheckboxGroup.Item value="c">Dark mode</CheckboxGroup.Item>
                      </CheckboxGroup.Root>
                    </Flex>
                    <Flex direction="column" gap="2">
                      <div className={styles.variantLabel}>Checkbox Cards</div>
                      <CheckboxCards.Root defaultValue={["1"]} columns="3">
                        <CheckboxCards.Item value="1">
                          <Flex direction="column">
                            <Text weight="bold">Free</Text>
                            <Text size="1">Basic features</Text>
                          </Flex>
                        </CheckboxCards.Item>
                        <CheckboxCards.Item value="2">
                          <Flex direction="column">
                            <Text weight="bold">Pro</Text>
                            <Text size="1">Advanced tools</Text>
                          </Flex>
                        </CheckboxCards.Item>
                        <CheckboxCards.Item value="3">
                          <Flex direction="column">
                            <Text weight="bold">Team</Text>
                            <Text size="1">Collaboration</Text>
                          </Flex>
                        </CheckboxCards.Item>
                      </CheckboxCards.Root>
                    </Flex>
                    <Flex direction="column" gap="2">
                      <div className={styles.variantLabel}>Radio Cards</div>
                      <RadioCards.Root defaultValue="1" columns="3">
                        <RadioCards.Item value="1">
                          <Flex direction="column">
                            <Text weight="bold">Opus</Text>
                            <Text size="1">Most capable</Text>
                          </Flex>
                        </RadioCards.Item>
                        <RadioCards.Item value="2">
                          <Flex direction="column">
                            <Text weight="bold">Sonnet</Text>
                            <Text size="1">Balanced</Text>
                          </Flex>
                        </RadioCards.Item>
                        <RadioCards.Item value="3">
                          <Flex direction="column">
                            <Text weight="bold">Haiku</Text>
                            <Text size="1">Fastest</Text>
                          </Flex>
                        </RadioCards.Item>
                      </RadioCards.Root>
                    </Flex>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="SegmentedControl"
                  description="Tab-like control for switching between mutually exclusive options. Used in settings."
                >
                  <SegmentedControl.Root defaultValue="tab1">
                    <SegmentedControl.Item value="tab1">Overview</SegmentedControl.Item>
                    <SegmentedControl.Item value="tab2">Changes</SegmentedControl.Item>
                    <SegmentedControl.Item value="tab3">History</SegmentedControl.Item>
                  </SegmentedControl.Root>
                </ComponentBlock>

                <ComponentBlock
                  name="Badge & Kbd"
                  description="Labels and keyboard shortcut indicators. Used in status displays and shortcut hints."
                >
                  <Flex direction="column" gap="3">
                    <div className={styles.variantRow}>
                      <Badge>Default</Badge>
                      <Badge color={settings.successColor}>Success</Badge>
                      <Badge color={settings.dangerColor}>Error</Badge>
                      <Badge color={settings.warningColor}>Warning</Badge>
                      <Badge color={settings.infoColor}>Info</Badge>
                      <Badge variant="surface">Surface</Badge>
                      <Badge variant="outline">Outline</Badge>
                    </div>
                    <div className={styles.variantRow}>
                      <Kbd>Ctrl</Kbd>
                      <Kbd>Shift</Kbd>
                      <Kbd>Enter</Kbd>
                      <Text size="2">
                        <Kbd>Cmd</Kbd> + <Kbd>K</Kbd>
                      </Text>
                    </div>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="Typography"
                  description="Text elements including Heading, Text, Strong, Quote, and Code."
                >
                  <Flex direction="column" gap="2">
                    <Heading size="6">Heading size 6</Heading>
                    <Heading size="4">Heading size 4</Heading>
                    <Heading size="2">Heading size 2</Heading>
                    <Text size="3">Regular text (size 3)</Text>
                    <Text size="2" color="gray">
                      Gray text (size 2)
                    </Text>
                    <Text size="1">Small text (size 1)</Text>
                    <Strong>Strong text</Strong>
                    <Quote>A quoted passage of text.</Quote>
                    <RadixCode>const x = 42;</RadixCode>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="Card"
                  description="Container for grouping related content. Used for workspace cards, settings sections."
                >
                  <Flex gap="3">
                    <Card style={{ width: 200 }}>
                      <Flex direction="column" gap="1">
                        <Heading size="2">Card Title</Heading>
                        <Text size="2" color="gray">
                          Card description with some content.
                        </Text>
                      </Flex>
                    </Card>
                    <Card variant="surface" style={{ width: 200 }}>
                      <Flex direction="column" gap="1">
                        <Heading size="2">Surface Card</Heading>
                        <Text size="2" color="gray">
                          With surface variant.
                        </Text>
                      </Flex>
                    </Card>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="Avatar"
                  description="User profile image or initial. Used in user settings and collaboration views."
                >
                  <div className={styles.variantRow}>
                    <Avatar size="1" fallback="A" />
                    <Avatar size="2" fallback="JD" />
                    <Avatar size="3" fallback="S" color={settings.infoColor} />
                    <Avatar size="4" fallback="IM" color={settings.successColor} />
                    <Avatar size="5" fallback="?" color={settings.dangerColor} />
                  </div>
                </ComponentBlock>

                <ComponentBlock
                  name="Callout"
                  description="Informational message with icon. Used for notices, tips, and warnings."
                >
                  <Flex direction="column" gap="3">
                    <Callout.Root>
                      <Callout.Icon>
                        <Info size={16} />
                      </Callout.Icon>
                      <Callout.Text>This is an informational callout message.</Callout.Text>
                    </Callout.Root>
                    <Callout.Root color={settings.dangerColor}>
                      <Callout.Icon>
                        <AlertTriangle size={16} />
                      </Callout.Icon>
                      <Callout.Text>This is an error/warning callout.</Callout.Text>
                    </Callout.Root>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="Tooltip, Popover, HoverCard"
                  description="Contextual information overlays. Used for hints, previews, and secondary info."
                >
                  <div className={styles.variantRow}>
                    <Tooltip content="This is a tooltip">
                      <Button variant="soft" size="1">
                        Hover for Tooltip
                      </Button>
                    </Tooltip>
                    <Popover.Root>
                      <Popover.Trigger>
                        <Button variant="soft" size="1">
                          Click for Popover
                        </Button>
                      </Popover.Trigger>
                      <Popover.Content>
                        <Flex direction="column" gap="2" style={{ maxWidth: 200 }}>
                          <Text size="2" weight="bold">
                            Popover Content
                          </Text>
                          <Text size="2">Additional details shown in a popover.</Text>
                        </Flex>
                      </Popover.Content>
                    </Popover.Root>
                    <HoverCard.Root>
                      <HoverCard.Trigger>
                        <Link size="2" style={{ cursor: "pointer" }}>
                          Hover for Card
                        </Link>
                      </HoverCard.Trigger>
                      <HoverCard.Content>
                        <Flex direction="column" gap="1" style={{ maxWidth: 200 }}>
                          <Heading size="2">HoverCard</Heading>
                          <Text size="2">Preview content on hover.</Text>
                        </Flex>
                      </HoverCard.Content>
                    </HoverCard.Root>
                  </div>
                </ComponentBlock>

                <ComponentBlock
                  name="DropdownMenu & ContextMenu"
                  description="Action menus triggered by click or right-click. Used in tab context menus, action menus."
                >
                  <div className={styles.variantRow}>
                    <DropdownMenu.Root>
                      <DropdownMenu.Trigger>
                        <Button variant="soft" size="1">
                          Dropdown Menu
                        </Button>
                      </DropdownMenu.Trigger>
                      <DropdownMenu.Content>
                        <DropdownMenu.Item>
                          <Copy size={14} /> Copy
                        </DropdownMenu.Item>
                        <DropdownMenu.Item>
                          <Clipboard size={14} /> Paste
                        </DropdownMenu.Item>
                        <DropdownMenu.Separator />
                        <DropdownMenu.Item color={settings.dangerColor}>
                          <Trash2 size={14} /> Delete
                        </DropdownMenu.Item>
                      </DropdownMenu.Content>
                    </DropdownMenu.Root>
                    <ContextMenu.Root>
                      <ContextMenu.Trigger>
                        <Box p="4" style={{ border: "1px dashed var(--gray-a6)", borderRadius: "var(--radius-2)" }}>
                          <Text size="2" color="gray">
                            Right-click here
                          </Text>
                        </Box>
                      </ContextMenu.Trigger>
                      <ContextMenu.Content>
                        <ContextMenu.Item>Edit</ContextMenu.Item>
                        <ContextMenu.Item>Duplicate</ContextMenu.Item>
                        <ContextMenu.Separator />
                        <ContextMenu.Item color={settings.dangerColor}>Delete</ContextMenu.Item>
                      </ContextMenu.Content>
                    </ContextMenu.Root>
                  </div>
                </ComponentBlock>

                <ComponentBlock
                  name="Tabs"
                  description="Tab navigation for switching content panels. Used in workspace panels, settings."
                >
                  <Tabs.Root defaultValue="tab1">
                    <Tabs.List>
                      <Tabs.Trigger value="tab1">Overview</Tabs.Trigger>
                      <Tabs.Trigger value="tab2">Changes</Tabs.Trigger>
                      <Tabs.Trigger value="tab3">Settings</Tabs.Trigger>
                    </Tabs.List>
                    <Box pt="3">
                      <Tabs.Content value="tab1">
                        <Text size="2">Overview content goes here.</Text>
                      </Tabs.Content>
                      <Tabs.Content value="tab2">
                        <Text size="2">Changes content goes here.</Text>
                      </Tabs.Content>
                      <Tabs.Content value="tab3">
                        <Text size="2">Settings content goes here.</Text>
                      </Tabs.Content>
                    </Box>
                  </Tabs.Root>
                </ComponentBlock>

                <ComponentBlock name="Table & DataList" description="Tabular and key-value data display.">
                  <Flex direction="column" gap="4">
                    <Table.Root>
                      <Table.Header>
                        <Table.Row>
                          <Table.ColumnHeaderCell>Name</Table.ColumnHeaderCell>
                          <Table.ColumnHeaderCell>Status</Table.ColumnHeaderCell>
                          <Table.ColumnHeaderCell>Updated</Table.ColumnHeaderCell>
                        </Table.Row>
                      </Table.Header>
                      <Table.Body>
                        <Table.Row>
                          <Table.Cell>Feature Branch</Table.Cell>
                          <Table.Cell>
                            <Badge color={settings.successColor}>Active</Badge>
                          </Table.Cell>
                          <Table.Cell>2 hours ago</Table.Cell>
                        </Table.Row>
                        <Table.Row>
                          <Table.Cell>Hotfix</Table.Cell>
                          <Table.Cell>
                            <Badge color={settings.warningColor}>Review</Badge>
                          </Table.Cell>
                          <Table.Cell>1 day ago</Table.Cell>
                        </Table.Row>
                      </Table.Body>
                    </Table.Root>
                    <DataList.Root>
                      <DataList.Item>
                        <DataList.Label>Status</DataList.Label>
                        <DataList.Value>
                          <Badge color={settings.successColor}>Active</Badge>
                        </DataList.Value>
                      </DataList.Item>
                      <DataList.Item>
                        <DataList.Label>Branch</DataList.Label>
                        <DataList.Value>main</DataList.Value>
                      </DataList.Item>
                      <DataList.Item>
                        <DataList.Label>Commit</DataList.Label>
                        <DataList.Value>
                          <RadixCode>abc1234</RadixCode>
                        </DataList.Value>
                      </DataList.Item>
                    </DataList.Root>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="Progress, Spinner, Skeleton, Slider"
                  description="Loading states and range inputs."
                >
                  <Flex direction="column" gap="4">
                    <Flex direction="column" gap="2">
                      <div className={styles.variantLabel}>Progress</div>
                      <Progress value={35} />
                      <Progress value={75} color={settings.successColor} />
                      <Progress value={100} color={settings.infoColor} />
                    </Flex>
                    <Flex gap="3" align="center">
                      <div className={styles.variantLabel}>Spinner</div>
                      <Spinner size="1" />
                      <Spinner size="2" />
                      <Spinner size="3" />
                    </Flex>
                    <Flex direction="column" gap="2">
                      <div className={styles.variantLabel}>Skeleton</div>
                      <Skeleton width="200px" height="16px" />
                      <Skeleton width="300px" height="16px" />
                      <Skeleton width="150px" height="16px" />
                    </Flex>
                    <Flex direction="column" gap="2">
                      <div className={styles.variantLabel}>Slider</div>
                      <Slider defaultValue={[50]} />
                      <Slider defaultValue={[25, 75]} />
                    </Flex>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock name="Separator & ScrollArea" description="Visual dividers and scrollable containers.">
                  <Flex direction="column" gap="3">
                    <Text size="2">Content above separator</Text>
                    <Separator size="4" />
                    <Text size="2">Content below separator</Text>
                    <div className={styles.variantLabel}>Scroll Area (horizontal)</div>
                    <ScrollArea type="hover" scrollbars="horizontal" style={{ maxWidth: 300 }}>
                      <Flex gap="2" style={{ width: 600 }}>
                        {Array.from({ length: 10 }, (_, i) => (
                          <Badge key={i}>Item {i + 1}</Badge>
                        ))}
                      </Flex>
                    </ScrollArea>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="Dialog & AlertDialog"
                  description="Modal overlays for focused interactions. Used for confirmations, forms, and alerts."
                >
                  <div className={styles.variantRow}>
                    <Dialog.Root>
                      <Dialog.Trigger>
                        <Button variant="soft" size="1">
                          Open Dialog
                        </Button>
                      </Dialog.Trigger>
                      <Dialog.Content>
                        <Dialog.Title>Dialog Title</Dialog.Title>
                        <Dialog.Description size="2">
                          This is a standard dialog for collecting input.
                        </Dialog.Description>
                        <Flex gap="3" mt="4" justify="end">
                          <Dialog.Close>
                            <Button variant="soft" color="gray">
                              Cancel
                            </Button>
                          </Dialog.Close>
                          <Dialog.Close>
                            <Button>Save</Button>
                          </Dialog.Close>
                        </Flex>
                      </Dialog.Content>
                    </Dialog.Root>
                    <AlertDialog.Root>
                      <AlertDialog.Trigger>
                        <Button variant="soft" size="1" color={settings.dangerColor}>
                          Open Alert
                        </Button>
                      </AlertDialog.Trigger>
                      <AlertDialog.Content>
                        <AlertDialog.Title>Are you sure?</AlertDialog.Title>
                        <AlertDialog.Description size="2">This action cannot be undone.</AlertDialog.Description>
                        <Flex gap="3" mt="4" justify="end">
                          <AlertDialog.Cancel>
                            <Button variant="soft" color="gray">
                              Cancel
                            </Button>
                          </AlertDialog.Cancel>
                          <AlertDialog.Action>
                            <Button color={settings.dangerColor}>Delete</Button>
                          </AlertDialog.Action>
                        </Flex>
                      </AlertDialog.Content>
                    </AlertDialog.Root>
                  </div>
                </ComponentBlock>
              </Section>

              {/* ============================================================
                SECTION: Status & Indicators
                ============================================================ */}
              <Section id="status-indicators" title="Status & Indicators">
                <ComponentBlock
                  name="PulsingCircle"
                  description="Animated status indicator. Used in ThinkingIndicator to show the agent is processing. src/components/PulsingCircle.tsx"
                >
                  <Flex gap="4" align="center">
                    <Flex direction="column" align="center" gap="1">
                      <PulsingCircle size="24px" />
                      <Text size="1" color="gray">
                        Pulsing (default)
                      </Text>
                    </Flex>
                    <Flex direction="column" align="center" gap="1">
                      <PulsingCircle size="32px" />
                      <Text size="1" color="gray">
                        Pulsing (larger)
                      </Text>
                    </Flex>
                    <Flex direction="column" align="center" gap="1">
                      <BlandCircle size="24px" />
                      <Text size="1" color="gray">
                        Bland (static)
                      </Text>
                    </Flex>
                    <Flex align="center" gap="2">
                      <PulsingCircle />
                      <Text size="2">Thinking...</Text>
                    </Flex>
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="Toast"
                  description="Notification toasts with 5 types. Displayed via ToastProvider at bottom-right. src/components/Toast.tsx"
                >
                  <ToastDemo
                    dangerColor={settings.dangerColor}
                    infoColor={settings.infoColor}
                    successColor={settings.successColor}
                    warningColor={settings.warningColor}
                  />
                </ComponentBlock>
              </Section>

              {/* ============================================================
                SECTION: Inputs & Editing
                ============================================================ */}
              <Section id="inputs-editing" title="Inputs & Editing">
                <ComponentBlock
                  name="InlineRenameInput"
                  description="Inline text editing that replaces display text. Used for workspace and tab renaming. src/components/InlineRenameInput.tsx"
                >
                  <InlineRenameDemo />
                </ComponentBlock>

                <ComponentBlock
                  name="TooltipIconButton"
                  description="IconButton wrapped with a Tooltip. The standard pattern for toolbar buttons. src/components/TooltipIconButton.tsx"
                >
                  <div className={styles.variantRow}>
                    <TooltipIconButton tooltipText="Copy to clipboard" icon={<Copy size={16} />} />
                    <TooltipIconButton tooltipText="Edit item" icon={<Edit3 size={16} />} />
                    <TooltipIconButton
                      tooltipText="Delete item"
                      icon={<Trash2 size={16} />}
                      color={settings.dangerColor}
                    />
                    <TooltipIconButton tooltipText="Notifications" icon={<Bell size={16} />} />
                    <TooltipIconButton tooltipText="Settings" icon={<Settings size={16} />} disabled />
                    <TooltipIconButton tooltipText="Loading..." icon={<Settings size={16} />} loading />
                  </div>
                </ComponentBlock>

                <ComponentBlock
                  name="Code"
                  description="Inline code display with optional underline and click styling. src/components/Code.tsx"
                >
                  <Flex direction="column" gap="2">
                    <Code>const x = 42;</Code>
                    <Code size="1">Small code (size 1)</Code>
                    <Code size="3">Larger code (size 3)</Code>
                    <Code isUnderlined>Underlined code</Code>
                    <Code isClickable onClick={() => alert("Clicked!")}>
                      Clickable code
                    </Code>
                  </Flex>
                </ComponentBlock>
              </Section>

              {/* ============================================================
                SECTION: Navigation & Selection
                ============================================================ */}
              <Section id="navigation-selection" title="Navigation & Selection">
                <ComponentBlock
                  name="TabBar (default)"
                  description="Draggable, reorderable tab bar with close buttons and overflow menu. Used for workspace and panel tabs. src/components/tabs/TabBar.tsx"
                >
                  <TabBarDemo />
                </ComponentBlock>

                <ComponentBlock
                  name="TabBar (compact)"
                  description="Compact variant with rounded tabs and horizontal scroll. Used for diff file tabs. src/components/tabs/TabBar.tsx"
                >
                  <CompactTabBarDemo />
                </ComponentBlock>

                <ComponentBlock
                  name="BranchSelectorCore"
                  description="Searchable branch dropdown with badge support. Used in workspace header for branch selection. src/components/BranchSelectorCore.tsx"
                >
                  <BranchSelectorCore
                    selectedBranch="main"
                    onBranchSelected={(branch) => alert(`Selected: ${branch}`)}
                    branches={MOCK_BRANCHES}
                    triggerContent={
                      <Button variant="soft" size="1">
                        <GitBranch size={14} /> main
                      </Button>
                    }
                  />
                </ComponentBlock>

                <ComponentBlock
                  name="ActionChip"
                  description="Quick action buttons shown below the chat input. Auto-submit (lightning) or draft (pencil) mode. src/components/actions/ActionChip.tsx"
                >
                  <div className={styles.variantRow}>
                    {MOCK_ACTIONS.map((action) => (
                      <ActionChip key={action.id} action={action} onClick={() => alert(`Action: ${action.name}`)} />
                    ))}
                    <ActionChip action={MOCK_ACTIONS[0]} onClick={() => {}} disabled />
                  </div>
                </ComponentBlock>
              </Section>

              {/* ============================================================
                SECTION: Content Display
                ============================================================ */}
              <Section id="content-display" title="Content Display">
                <ComponentBlock
                  name="MarkdownBlock"
                  description="Renders markdown content with GFM support, code blocks, tables, and emoji. Used for agent messages. src/components/MarkdownBlock.tsx"
                >
                  <Box style={{ maxWidth: 600 }}>
                    <MarkdownBlock content={MOCK_MARKDOWN} />
                  </Box>
                </ComponentBlock>

                <ComponentBlock
                  name="AskUserQuestion (single)"
                  description="Multi-choice question card for agent-to-user interaction. Single select with keyboard navigation. src/pages/workspace/components/AskUserQuestion.tsx"
                >
                  <Box style={{ maxWidth: 600 }}>
                    <AskUserQuestion
                      taskId="gallery-demo"
                      questionData={MOCK_QUESTION_DATA}
                      onSubmit={(answers) => alert(JSON.stringify(answers, null, 2))}
                      onDismiss={() => alert("Dismissed")}
                    />
                  </Box>
                </ComponentBlock>

                <ComponentBlock
                  name="AskUserQuestion (multi-question)"
                  description="Multi-question flow with dot navigation and mixed single/multi-select modes."
                >
                  <Box style={{ maxWidth: 600 }}>
                    <AskUserQuestion
                      taskId="gallery-demo-multi"
                      questionData={MOCK_MULTI_QUESTION_DATA}
                      onSubmit={(answers) => alert(JSON.stringify(answers, null, 2))}
                      onDismiss={() => alert("Dismissed")}
                    />
                  </Box>
                </ComponentBlock>
              </Section>

              {/* ============================================================
                SECTION: Dialogs & Modals
                ============================================================ */}
              <Section id="dialogs-modals" title="Dialogs & Modals">
                <ComponentBlock
                  name="DeleteConfirmationDialog"
                  description="Confirmation modal for destructive actions (workspace/agent deletion). src/components/DeleteConfirmationDialog.tsx"
                >
                  <DeleteDialogDemo dangerColor={settings.dangerColor} />
                </ComponentBlock>

                <ComponentBlock
                  name="ActionDialog"
                  description="Create/edit dialog for custom actions with name, prompt, auto-submit toggle, and group assignment. src/components/actions/ActionDialog.tsx"
                >
                  <ActionDialogDemo />
                </ComponentBlock>

                <ComponentBlock
                  name="ImageLightbox"
                  description="Full-screen media viewer with navigation for images and videos. src/components/ImageLightbox.tsx"
                >
                  <ImageLightboxDemo />
                </ComponentBlock>
              </Section>

              {/* ============================================================
                SECTION: Cards & Banners
                ============================================================ */}
              <Section id="cards-banners" title="Cards & Banners">
                <ComponentBlock
                  name="WarningStatusBanner"
                  description="Yellow warning banner shown at top of page. Used for missing dependencies or stale workspaces. src/components/WarningStatusBanner.tsx"
                >
                  <Flex direction="column" gap="3">
                    <WarningStatusBanner
                      message="Your workspace is out of date."
                      linkText="Update now"
                      onLinkClick={() => alert("Update")}
                    />
                    <WarningStatusBanner message="Git is not installed. Some features will be unavailable." />
                  </Flex>
                </ComponentBlock>

                <ComponentBlock
                  name="FilePreview (states)"
                  description="Compact file preview thumbnails for attached images/PDFs. Shows loading, error, and success states. src/components/FilePreview.tsx"
                >
                  <Flex direction="column" gap="3">
                    <div className={styles.variantLabel}>Compact mode (no file URL - shows error)</div>
                    <Flex gap="2">
                      {/* We can only show the error/loading states without a backend */}
                      <Box
                        style={{
                          width: 60,
                          height: 60,
                          border: "1px dashed var(--gray-a5)",
                          borderRadius: "var(--radius-2)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        <Text size="1" color="gray">
                          PDF
                        </Text>
                      </Box>
                      <Box
                        style={{
                          width: 60,
                          height: 60,
                          border: "1px dashed var(--gray-a5)",
                          borderRadius: "var(--radius-2)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        <Text size="1" color="gray">
                          IMG
                        </Text>
                      </Box>
                      <Box
                        style={{
                          width: 60,
                          height: 60,
                          border: "1px dashed var(--red-a3)",
                          borderRadius: "var(--radius-2)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        <Text size="1" color={settings.dangerColor}>
                          ERR
                        </Text>
                      </Box>
                    </Flex>
                  </Flex>
                </ComponentBlock>
              </Section>
            </main>
          </div>
        </div>
      </JotaiProvider>
    </Theme>
  );
};

const resolveAppearance = (appearance: "light" | "dark" | "system"): "light" | "dark" => {
  if (appearance === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return appearance;
};

export const ComponentGalleryPage = (): ReactElement => {
  const themeBuilderSettings = useAtomValue(themeBuilderSettingsAtom);
  const setThemeBuilderSettings = useSetAtom(themeBuilderSettingsAtom);

  const [settings, setSettings] = useState<ThemeSettings>(() => ({
    ...themeBuilderSettings,
    primaryFont: themeBuilderSettings.primaryFont ?? "System default",
    hexOverrides: themeBuilderSettings.hexOverrides ?? DEFAULT_HEX_OVERRIDES,
    codeFont: themeBuilderSettings.codeFont ?? "System default",
    appearance: resolveAppearance(themeBuilderSettings.appearance),
  }));

  const handleSettingsChange = useCallback((patch: Partial<ThemeSettings>): void => {
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  const handleSave = useCallback((): void => {
    setThemeBuilderSettings(settings);
  }, [settings, setThemeBuilderSettings]);

  return <GalleryContent settings={settings} onSettingsChange={handleSettingsChange} onSave={handleSave} />;
};
