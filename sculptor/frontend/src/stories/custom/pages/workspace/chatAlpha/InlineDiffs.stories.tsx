/**
 * Visual-only mock stories for the proposed inline diff design:
 *  - Edit/Write tool lines expand to show a pierre diff (instead of raw text)
 *  - A turn-level summary appears as a hover popover on the footer's +/- stats
 *
 * These are visual mock stories — new components are replicated here so that
 * design details can be iterated in Storybook before building the real thing.
 */

import { Badge } from "@radix-ui/themes";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChevronRightIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useEffect, useState } from "react";

import chatStyles from "~/pages/workspace/chatAlpha/AlphaChatView.module.scss";
import { PulsingDot } from "~/pages/workspace/chatAlpha/pillAnimations";
import { TurnFooter } from "~/pages/workspace/chatAlpha/TurnFooter";
import { PierreDiffView } from "~/pages/workspace/diffPanel/PierreDiffView.tsx";

import {
  DIFF_AUTH_MIDDLEWARE,
  DIFF_CORS_FIX,
  DIFF_MIGRATION_NEW,
  DIFF_PAGINATION_FIX,
  DIFF_TEST_USER,
  DIFF_USER_MODEL,
  DIFF_VALIDATORS_NEW,
  DIFF_WORKSPACE_DATETIME,
} from "./fixtures/diffData.ts";

/** Scrollable chat body container. */
const ChatBody = ({ children }: { children: ReactElement | Array<ReactElement | null> }): ReactElement => (
  <div style={{ height: "100%", overflowY: "auto", width: "100%" }}>
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        maxWidth: "680px",
        margin: "0 auto",
        padding: "24px 32px 40px",
      }}
    >
      {children}
    </div>
  </div>
);

type MsgShellProps = {
  role: "user" | "assistant";
  timestamp: string;
  children: ReactElement | Array<ReactElement | null>;
  newCycle?: boolean;
};

/** Message wrapper: role label + timestamp header. */
const MsgShell = ({ role, timestamp, children, newCycle = false }: MsgShellProps): ReactElement => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      gap: "4px",
      ...(newCycle ? { marginTop: "24px" } : {}),
    }}
  >
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
      <span
        style={{
          color: role === "user" ? "var(--accent-9)" : "var(--gray-9)",
          fontSize: "var(--font-size-1)",
          fontWeight: "var(--font-weight-bold)",
        }}
      >
        {role === "user" ? "User" : "Assistant"}
      </span>
      <span style={{ color: "var(--gray-7)", fontSize: "var(--font-size-1)", fontFamily: "var(--code-font-family)" }}>
        {timestamp}
      </span>
    </div>
    {children}
  </div>
);

const MsgText = ({ children }: { children: ReactNode }): ReactElement => (
  <p className={chatStyles.messageText}>{children}</p>
);

/**
 * Detect the current Radix theme appearance from the DOM.
 * The Storybook decorator sets `class="light"` or `class="dark"` on the
 * `<div data-radix-theme>` wrapper, so we observe that to stay in sync.
 */
const useStoryTheme = (): "light" | "dark" => {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const el = document.querySelector("[data-radix-theme]");
    if (!el) return;
    const update = (): void => {
      setTheme(el.classList.contains("dark") ? "dark" : "light");
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(el, { attributes: true, attributeFilter: ["class"] });
    return (): void => observer.disconnect();
  }, []);
  return theme;
};

/** Non-edit tool (Read, Bash, etc.): collapsed, semi-opaque. */
const CollapsedToolLine = ({ name, input }: { name: string; input: string }): ReactElement => (
  <div className={chatStyles.toolLine}>
    <div className={chatStyles.toolHeader}>
      <ChevronRightIcon size={12} className={chatStyles.chevronClosed} />
      <span className={chatStyles.toolName}>{name}</span>
      <span className={chatStyles.toolInput}>{input}</span>
    </div>
  </div>
);

/** Edit/Write tool: expands to show a PierreDiffView. */
const DiffToolLine = ({
  name,
  filePath,
  diffString,
  defaultExpanded = false,
  isExecuting = false,
}: {
  name: string;
  filePath: string;
  diffString?: string;
  defaultExpanded?: boolean;
  isExecuting?: boolean;
}): ReactElement => {
  const themeType = useStoryTheme();
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const lineClass = isExecuting
    ? `${chatStyles.toolLine} ${chatStyles.executingToolLine}`
    : isExpanded
      ? `${chatStyles.toolLine} ${chatStyles.expandedToolLine}`
      : chatStyles.toolLine;

  return (
    <div
      className={lineClass}
      onClick={(): void => setIsExpanded((p) => !p)}
      role="button"
      tabIndex={0}
      onKeyDown={(e): void => {
        if (e.key === "Enter" || e.key === " ") setIsExpanded((p) => !p);
      }}
    >
      <div className={chatStyles.toolHeader}>
        {isExecuting ? (
          <PulsingDot />
        ) : (
          <ChevronRightIcon size={12} className={isExpanded ? chatStyles.chevronOpen : chatStyles.chevronClosed} />
        )}
        <span className={chatStyles.toolName}>{name}</span>
        <span className={chatStyles.toolInput}>{filePath}</span>
      </div>
      {isExpanded && diffString && (
        <div
          style={{ marginTop: "6px", maxHeight: "500px", overflow: "auto" }}
          onClick={(e): void => e.stopPropagation()}
        >
          <PierreDiffView
            diffString={diffString}
            viewType="unified"
            overflow="wrap"
            themeType={themeType}
            hideHandle={true}
          />
        </div>
      )}
    </div>
  );
};

/** Collapsed tool group header: "N Called Tools". */
const ToolGroupHeader = ({ count, summary }: { count: number; summary?: string }): ReactElement => (
  <div className={chatStyles.toolGroupHeader}>
    <ChevronRightIcon size={12} className={chatStyles.chevronClosed} />
    <Badge size="1" variant="soft">
      {count}
    </Badge>
    <span className={chatStyles.toolName}>Called Tools</span>
    {summary && <span className={chatStyles.toolInput}>{summary}</span>}
  </div>
);

/** Tool result: error styling. */
const ToolError = ({ text }: { text: string }): ReactElement => (
  <pre className={`${chatStyles.toolResult} ${chatStyles.toolResultError}`}>{text}</pre>
);

/** Subagent indent wrapper. */
const SubagentTools = ({ children }: { children: ReactElement | Array<ReactElement | null> }): ReactElement => (
  <div className={chatStyles.subagentTools}>{children}</div>
);

const DiffToolLineShowcase = (): ReactElement => (
  <div
    style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "24px", maxWidth: "680px", width: "100%" }}
  >
    <div>
      <p style={{ color: "var(--gray-9)", fontSize: "var(--font-size-1)", marginBottom: "6px" }}>
        Collapsed (click to expand)
      </p>
      <DiffToolLine name="Edit" filePath="sculptor/backend/utils/pagination.py" diffString={DIFF_PAGINATION_FIX} />
    </div>

    <div>
      <p style={{ color: "var(--gray-9)", fontSize: "var(--font-size-1)", marginBottom: "6px" }}>
        Expanded — small diff (1 line changed)
      </p>
      <DiffToolLine
        name="Edit"
        filePath="sculptor/backend/utils/pagination.py"
        diffString={DIFF_PAGINATION_FIX}
        defaultExpanded={true}
      />
    </div>

    <div>
      <p style={{ color: "var(--gray-9)", fontSize: "var(--font-size-1)", marginBottom: "6px" }}>Expanded — new file</p>
      <DiffToolLine
        name="Write"
        filePath="sculptor/backend/utils/validators.py"
        diffString={DIFF_VALIDATORS_NEW}
        defaultExpanded={true}
      />
    </div>

    <div>
      <p style={{ color: "var(--gray-9)", fontSize: "var(--font-size-1)", marginBottom: "6px" }}>
        Executing (pulsing dot, not clickable)
      </p>
      <DiffToolLine name="Edit" filePath="sculptor/backend/models/user.py" isExecuting={true} />
    </div>

    <div>
      <p style={{ color: "var(--gray-9)", fontSize: "var(--font-size-1)", marginBottom: "6px" }}>
        Non-edit tool (Read) — no diff, stays collapsed
      </p>
      <CollapsedToolLine name="Read" input="sculptor/backend/models/user.py" />
    </div>
  </div>
);

const Scenario1 = (): ReactElement => (
  <ChatBody>
    <MsgShell role="user" timestamp="+0s">
      <MsgText>Fix the off-by-one error in paginate_results</MsgText>
    </MsgShell>

    <MsgShell role="assistant" timestamp="+1s">
      <MsgText>
        I see the issue — the slice end is off by one. I&apos;ll remove the{" "}
        <code
          style={{
            fontFamily: "var(--code-font-family)",
            background: "var(--gray-3)",
            padding: "1px 4px",
            borderRadius: 3,
          }}
        >
          - 1
        </code>{" "}
        from the end offset.
      </MsgText>

      <CollapsedToolLine name="Read" input="sculptor/backend/utils/pagination.py" />

      <DiffToolLine
        name="Edit"
        filePath="sculptor/backend/utils/pagination.py"
        diffString={DIFF_PAGINATION_FIX}
        defaultExpanded={true}
      />

      <MsgText>Fixed. The slice now correctly includes the last item on each page.</MsgText>

      <TurnFooter
        metrics={{ durationSeconds: 8.0, inputTokens: 500, outputTokens: 400 }}
        files={[{ path: "sculptor/backend/utils/pagination.py", status: "modified" }]}
      />
    </MsgShell>
  </ChatBody>
);

const Scenario2 = (): ReactElement => (
  <ChatBody>
    <MsgShell role="user" timestamp="+0s">
      <MsgText>Add email validation to the user model with tests</MsgText>
    </MsgShell>

    <MsgShell role="assistant" timestamp="+2s">
      <MsgText>
        I&apos;ll add a{" "}
        <code
          style={{
            fontFamily: "var(--code-font-family)",
            background: "var(--gray-3)",
            padding: "1px 4px",
            borderRadius: 3,
          }}
        >
          validate_email
        </code>{" "}
        method using a shared utility, and write tests for it.
      </MsgText>

      <CollapsedToolLine name="Read" input="sculptor/backend/models/user.py" />

      <DiffToolLine name="Edit" filePath="sculptor/backend/models/user.py" diffString={DIFF_USER_MODEL} />

      <DiffToolLine
        name="Write"
        filePath="sculptor/backend/utils/validators.py"
        diffString={DIFF_VALIDATORS_NEW}
        defaultExpanded={true}
      />

      <CollapsedToolLine name="Read" input="sculptor/backend/tests/test_user.py" />

      <DiffToolLine name="Edit" filePath="sculptor/backend/tests/test_user.py" diffString={DIFF_TEST_USER} />

      <MsgText>Added the method, extracted the regex into a shared utility, and wrote three tests.</MsgText>

      <TurnFooter
        metrics={{ durationSeconds: 18.0, inputTokens: 2_000, outputTokens: 1_400 }}
        files={[
          { path: "sculptor/backend/models/user.py", status: "modified" },
          { path: "sculptor/backend/utils/validators.py", status: "new" },
          { path: "sculptor/backend/tests/test_user.py", status: "modified" },
        ]}
      />
    </MsgShell>
  </ChatBody>
);

const Scenario3 = (): ReactElement => (
  <ChatBody>
    <MsgShell role="user" timestamp="+0s">
      <MsgText>Refactor auth middleware to use the new session store</MsgText>
    </MsgShell>

    <MsgShell role="assistant" timestamp="+1s">
      <MsgText>I&apos;ll update the import and switch to the new SessionStore API.</MsgText>

      <CollapsedToolLine name="Read" input="sculptor/backend/middleware/auth.py" />

      {/* Completed edit — already expandable */}
      <DiffToolLine
        name="Edit"
        filePath="sculptor/backend/middleware/auth.py"
        diffString={DIFF_AUTH_MIDDLEWARE}
        defaultExpanded={true}
      />

      {/* Currently executing — pulsing dot, no diff yet */}
      <DiffToolLine name="Edit" filePath="sculptor/backend/sessions/store.py" isExecuting={true} />

      {/* No footer yet — turn is still in progress */}
    </MsgShell>
  </ChatBody>
);

const Scenario4 = (): ReactElement => (
  <ChatBody>
    <MsgShell role="user" timestamp="+0s">
      <MsgText>Split utils.py into separate helpers modules and remove the original</MsgText>
    </MsgShell>

    <MsgShell role="assistant" timestamp="+3s">
      <MsgText>I&apos;ll split the utilities into focused modules and clean up the old file.</MsgText>

      <ToolGroupHeader count={6} summary="Read, Write, Write, Edit, Bash, Bash" />

      <MsgText>
        Split into{" "}
        <code
          style={{
            fontFamily: "var(--code-font-family)",
            background: "var(--gray-3)",
            padding: "1px 4px",
            borderRadius: 3,
          }}
        >
          string_helpers.py
        </code>{" "}
        and{" "}
        <code
          style={{
            fontFamily: "var(--code-font-family)",
            background: "var(--gray-3)",
            padding: "1px 4px",
            borderRadius: 3,
          }}
        >
          date_helpers.py
        </code>
        , updated imports in{" "}
        <code
          style={{
            fontFamily: "var(--code-font-family)",
            background: "var(--gray-3)",
            padding: "1px 4px",
            borderRadius: 3,
          }}
        >
          __init__.py
        </code>
        , and deleted the original.
      </MsgText>

      <TurnFooter
        metrics={{ durationSeconds: 24.0, inputTokens: 3_200, outputTokens: 1_600 }}
        files={[
          { path: "sculptor/backend/utils/string_helpers.py", status: "new" },
          { path: "sculptor/backend/utils/date_helpers.py", status: "new" },
          { path: "sculptor/backend/utils/__init__.py", status: "modified" },
          { path: "sculptor/backend/utils/utils.py", status: "deleted" },
        ]}
      />
    </MsgShell>
  </ChatBody>
);

const Scenario5 = (): ReactElement => (
  <ChatBody>
    <MsgShell role="assistant" timestamp="+2s">
      <MsgText>Let me update the CORS config.</MsgText>

      {/* First edit succeeds */}
      <DiffToolLine name="Edit" filePath="sculptor/backend/config.py" diffString={DIFF_PAGINATION_FIX} />

      {/* Second edit fails — shows error in result */}
      <div className={chatStyles.toolLine} style={{ opacity: 1 }} onClick={undefined} role="button" tabIndex={0}>
        <div className={chatStyles.toolHeader}>
          <ChevronRightIcon size={12} className={chatStyles.chevronOpen} />
          <span className={chatStyles.toolName}>Edit</span>
          <span className={chatStyles.toolInput}>sculptor/backend/middleware/cors.py</span>
        </div>
        <ToolError
          text={`Error: old_string not found in file.

Searched for:
    ALLOWED_ORIGINS = ["localhost"]

Did you mean one of these?
    ALLOWED_ORIGINS = ["localhost", "127.0.0.1"]  (line 12)`}
        />
      </div>

      <MsgText>The CORS config was already updated. Let me re-read and apply the fix.</MsgText>

      <CollapsedToolLine name="Read" input="sculptor/backend/middleware/cors.py" />

      <DiffToolLine name="Edit" filePath="sculptor/backend/middleware/cors.py" diffString={DIFF_CORS_FIX} />

      <MsgText>Fixed. Both config files are updated.</MsgText>

      <TurnFooter
        metrics={{ durationSeconds: 15.0, inputTokens: 1_300, outputTokens: 800 }}
        files={[
          { path: "sculptor/backend/config.py", status: "modified" },
          { path: "sculptor/backend/middleware/cors.py", status: "modified" },
        ]}
      />
    </MsgShell>
  </ChatBody>
);

const Scenario6 = (): ReactElement => (
  <ChatBody>
    <MsgShell role="user" timestamp="+0s">
      <MsgText>Migrate the entire ORM layer to use the new query builder</MsgText>
    </MsgShell>

    <MsgShell role="assistant" timestamp="+3s">
      <MsgText>I&apos;ll convert all database queries to the new builder pattern and update the tests.</MsgText>

      <ToolGroupHeader count={12} summary="Read, Edit, Edit, Read, Edit, Edit, Edit, Read, Edit, Edit, Edit, Bash" />

      <MsgText>All queries now use the builder pattern. Tests updated to match.</MsgText>

      <TurnFooter
        metrics={{ durationSeconds: 45.0, inputTokens: 8_000, outputTokens: 4_600 }}
        files={[
          { path: "sculptor/backend/db/queries/users.py", status: "modified" },
          { path: "sculptor/backend/db/queries/workspaces.py", status: "modified" },
          { path: "sculptor/backend/db/queries/sessions.py", status: "modified" },
          { path: "sculptor/backend/db/builder.py", status: "new" },
          { path: "sculptor/backend/db/base.py", status: "modified" },
          { path: "sculptor/backend/tests/test_queries.py", status: "modified" },
          { path: "sculptor/backend/tests/test_builder.py", status: "new" },
          { path: "sculptor/backend/db/legacy_orm.py", status: "deleted" },
        ]}
      />
    </MsgShell>
  </ChatBody>
);

const Scenario7 = (): ReactElement => (
  <ChatBody>
    {/* Turn 1 */}
    <MsgShell role="user" timestamp="+0s">
      <MsgText>Add a created_at field to the Workspace model</MsgText>
    </MsgShell>

    <MsgShell role="assistant" timestamp="+1s">
      <MsgText>I&apos;ll add the timestamp field with a default value.</MsgText>

      <CollapsedToolLine name="Read" input="sculptor/backend/models/workspace.py" />
      <DiffToolLine name="Edit" filePath="sculptor/backend/models/workspace.py" diffString={DIFF_WORKSPACE_DATETIME} />

      <MsgText>
        Added{" "}
        <code
          style={{
            fontFamily: "var(--code-font-family)",
            background: "var(--gray-3)",
            padding: "1px 4px",
            borderRadius: 3,
          }}
        >
          created_at: datetime
        </code>{" "}
        with a default of{" "}
        <code
          style={{
            fontFamily: "var(--code-font-family)",
            background: "var(--gray-3)",
            padding: "1px 4px",
            borderRadius: 3,
          }}
        >
          datetime.now(UTC)
        </code>
        .
      </MsgText>

      <TurnFooter
        metrics={{ durationSeconds: 8.0, inputTokens: 500, outputTokens: 400 }}
        files={[{ path: "sculptor/backend/models/workspace.py", status: "modified" }]}
      />
    </MsgShell>

    {/* Turn 2 */}
    <MsgShell role="user" timestamp="+35s" newCycle={true}>
      <MsgText>Also add a migration for this column</MsgText>
    </MsgShell>

    <MsgShell role="assistant" timestamp="+36s">
      <MsgText>I&apos;ll create an Alembic migration for the new column.</MsgText>

      <DiffToolLine
        name="Write"
        filePath="sculptor/backend/migrations/002_add_workspace_created_at.py"
        diffString={DIFF_MIGRATION_NEW}
        defaultExpanded={true}
      />

      <MsgText>Migration created. Run it with alembic upgrade head.</MsgText>

      <TurnFooter
        metrics={{ durationSeconds: 11.0, inputTokens: 900, outputTokens: 600 }}
        files={[
          {
            path: "sculptor/backend/migrations/002_add_workspace_created_at.py",
            status: "new",
          },
        ]}
      />
    </MsgShell>
  </ChatBody>
);

const Scenario8 = (): ReactElement => (
  <ChatBody>
    <MsgShell role="user" timestamp="+0s">
      <MsgText>Add input validation to all API endpoints</MsgText>
    </MsgShell>

    <MsgShell role="assistant" timestamp="+2s">
      <MsgText>I&apos;ll use subagents to add Pydantic validation to each endpoint group in parallel.</MsgText>

      {/* Parent: edit shared schemas file */}
      <DiffToolLine name="Edit" filePath="sculptor/backend/api/schemas.py" diffString={DIFF_VALIDATORS_NEW} />

      {/* Subagent 1 */}
      <div className={chatStyles.toolLine} style={{ opacity: 0.7 }}>
        <div className={chatStyles.toolHeader}>
          <ChevronRightIcon size={12} className={chatStyles.chevronOpen} />
          <span className={chatStyles.toolName} style={{ color: "var(--accent-9)" }}>
            Agent
          </span>
          <span className={chatStyles.toolInput}>Validate user endpoints</span>
        </div>
      </div>
      <SubagentTools>
        <CollapsedToolLine name="Read" input="sculptor/backend/api/users.py" />
        <DiffToolLine name="Edit" filePath="sculptor/backend/api/users.py" diffString={DIFF_USER_MODEL} />
      </SubagentTools>

      {/* Subagent 2 */}
      <div className={chatStyles.toolLine} style={{ opacity: 0.7 }}>
        <div className={chatStyles.toolHeader}>
          <ChevronRightIcon size={12} className={chatStyles.chevronOpen} />
          <span className={chatStyles.toolName} style={{ color: "var(--accent-9)" }}>
            Agent
          </span>
          <span className={chatStyles.toolInput}>Validate workspace endpoints</span>
        </div>
      </div>
      <SubagentTools>
        <CollapsedToolLine name="Read" input="sculptor/backend/api/workspaces.py" />
        <DiffToolLine name="Edit" filePath="sculptor/backend/api/workspaces.py" diffString={DIFF_WORKSPACE_DATETIME} />
      </SubagentTools>

      <MsgText>Added Pydantic validation to all user and workspace endpoints.</MsgText>

      <TurnFooter
        metrics={{ durationSeconds: 22.0, inputTokens: 3_500, outputTokens: 1_700 }}
        files={[
          { path: "sculptor/backend/api/schemas.py", status: "modified" },
          { path: "sculptor/backend/api/users.py", status: "modified" },
          { path: "sculptor/backend/api/workspaces.py", status: "modified" },
        ]}
      />
    </MsgShell>
  </ChatBody>
);

const meta = {
  title: "Chat Alpha/Inline Diffs",
  parameters: {
    layout: "fullscreen",
    panelsFullscreen: true,
  },
} satisfies Meta;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

const scenarioDecorator = (Story: () => ReactElement): ReactElement => (
  <div style={{ height: "500px", display: "flex" }}>
    <Story />
  </div>
);

const componentDecorator = (Story: () => ReactElement): ReactElement => (
  <div style={{ display: "flex", justifyContent: "center", padding: "24px", minHeight: "100vh" }}>
    <Story />
  </div>
);

/** Edit tool line with pierre diff — all visual states */
export const DiffToolLineComponent: Story = {
  name: "Component: Diff Tool Line",
  render: (): ReactElement => <DiffToolLineShowcase />,
  decorators: [componentDecorator],
};

/** Scenario 1: Simple single-file edit */
export const S1SimpleEdit: Story = {
  name: "S1: Simple Edit",
  render: (): ReactElement => <Scenario1 />,
  decorators: [scenarioDecorator],
};

/** Scenario 2: Multiple files changed in one turn */
export const S2MultiFileTurn: Story = {
  name: "S2: Multi-File Turn",
  render: (): ReactElement => <Scenario2 />,
  decorators: [scenarioDecorator],
};

/** Scenario 3: Turn still in progress — no summary yet */
export const S3StreamingInProgress: Story = {
  name: "S3: Streaming / In Progress",
  render: (): ReactElement => <Scenario3 />,
  decorators: [scenarioDecorator],
};

/** Scenario 4: New, deleted, and renamed files in the summary */
export const S4NewAndDeletedFiles: Story = {
  name: "S4: New & Deleted Files",
  render: (): ReactElement => <Scenario4 />,
  decorators: [scenarioDecorator],
};

/** Scenario 5: A tool fails mid-turn, retried and succeeded */
export const S5ErrorDuringEdit: Story = {
  name: "S5: Error During Edit",
  render: (): ReactElement => <Scenario5 />,
  decorators: [scenarioDecorator],
};

/** Scenario 6: Large turn — many files, tool group collapsed */
export const S6LargeDiff: Story = {
  name: "S6: Large Diff / Many Files",
  render: (): ReactElement => <Scenario6 />,
  decorators: [scenarioDecorator],
};

/** Scenario 7: Two prompt/response cycles with per-turn summaries */
export const S7MultiTurn: Story = {
  name: "S7: Multi-Turn Conversation",
  render: (): ReactElement => <Scenario7 />,
  decorators: [scenarioDecorator],
};

/** Scenario 8: Subagent edits aggregated into the parent turn summary */
export const S8SubagentEdits: Story = {
  name: "S8: Subagent Edits",
  render: (): ReactElement => <Scenario8 />,
  decorators: [scenarioDecorator],
};
