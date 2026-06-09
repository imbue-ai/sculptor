import { Badge, Box, Button, Flex, Spinner, Text, TextField } from "@radix-ui/themes";
import { PanelHeader, usePluginSetting, useWorkspaceBranch } from "@sculptor/plugin-sdk";
import { AlertCircle, Hash } from "lucide-react";
import { type ReactElement, useEffect, useMemo, useState } from "react";

const LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql";

type LinearIssue = {
  identifier: string;
  title: string;
  url: string;
  description: string | null;
  priorityLabel: string | null;
  state: { name: string; type: string; color: string } | null;
  assignee: { displayName: string } | null;
};

type Ticket = { key: string; number: number; identifier: string };

/**
 * Pull a Linear ticket out of a git branch. Sculptor branches follow
 * `<user>/<ticket-id>-<title>` (e.g. `maciek/scu-1436-fix-flicker`), so the
 * first `<letters>-<digits>` run is the ticket.
 */
const parseTicket = (branch: string | null): Ticket | null => {
  if (!branch) return null;
  const match = branch.match(/([a-zA-Z]{2,})-(\d+)/);
  if (!match) return null;
  const key = match[1].toUpperCase();
  const number = Number(match[2]);
  return { key, number, identifier: `${key}-${number}` };
};

const ISSUE_QUERY = `query ($key: String!, $num: Float!) {
  issues(filter: { team: { key: { eq: $key } }, number: { eq: $num } }, first: 1) {
    nodes {
      identifier
      title
      url
      description
      priorityLabel
      state { name type color }
      assignee { displayName }
    }
  }
}`;

const fetchIssue = async (apiKey: string, ticket: Ticket, signal: AbortSignal): Promise<LinearIssue | null> => {
  const res = await fetch(LINEAR_GRAPHQL_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: apiKey },
    body: JSON.stringify({ query: ISSUE_QUERY, variables: { key: ticket.key, num: ticket.number } }),
    signal,
  });
  if (res.status === 400 || res.status === 401) {
    throw new Error("Linear rejected the API key — check it in plugin settings.");
  }
  if (!res.ok) {
    throw new Error(`Linear API error: HTTP ${res.status}`);
  }
  const json = (await res.json()) as {
    data?: { issues?: { nodes?: Array<LinearIssue> } };
    errors?: Array<{ message?: string }>;
  };
  if (json.errors && json.errors.length > 0) {
    throw new Error(json.errors[0]?.message ?? "Linear GraphQL error");
  }
  return json.data?.issues?.nodes?.[0] ?? null;
};

const EmptyState = ({ children }: { children: string }): ReactElement => (
  <Flex direction="column" align="center" justify="center" gap="2" p="5" style={{ flexGrow: 1 }}>
    <AlertCircle size={20} color="var(--gray-8)" />
    <Text size="2" color="gray" align="center">
      {children}
    </Text>
  </Flex>
);

const IssueCard = ({ issue }: { issue: LinearIssue }): ReactElement => (
  <Flex direction="column" gap="3" p="3" style={{ overflowY: "auto", flexGrow: 1 }}>
    <Flex align="center" gap="2">
      <Text size="1" color="gray" style={{ fontFamily: "var(--code-font-family)" }}>
        {issue.identifier}
      </Text>
      {issue.state && (
        <Flex align="center" gap="1">
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: issue.state.color || "var(--gray-8)",
              display: "inline-block",
            }}
          />
          <Text size="1" color="gray">
            {issue.state.name}
          </Text>
        </Flex>
      )}
      {issue.priorityLabel && issue.priorityLabel !== "No priority" && (
        <Badge size="1" color="gray" variant="soft">
          {issue.priorityLabel}
        </Badge>
      )}
    </Flex>

    <Text size="3" weight="medium">
      {issue.title}
    </Text>

    {issue.assignee && (
      <Text size="1" color="gray">
        Assigned to {issue.assignee.displayName}
      </Text>
    )}

    {issue.description && (
      <Text size="1" color="gray" style={{ whiteSpace: "pre-wrap" }}>
        {issue.description.length > 320 ? `${issue.description.slice(0, 320)}…` : issue.description}
      </Text>
    )}

    <Box>
      <Button size="1" variant="soft" onClick={() => window.open(issue.url, "_blank")}>
        Open in Linear
      </Button>
    </Box>
  </Flex>
);

const LinearPanel = (): ReactElement => {
  const branch = useWorkspaceBranch();
  const [apiKey] = usePluginSetting("apiKey");
  const ticket = useMemo(() => parseTicket(branch), [branch]);

  const [issue, setIssue] = useState<LinearIssue | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!apiKey || !ticket) {
      setIssue(null);
      setStatus("idle");
      setError("");
      return;
    }
    const controller = new AbortController();
    setStatus("loading");
    setError("");
    fetchIssue(apiKey, ticket, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setIssue(result);
        setStatus("idle");
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
        setStatus("error");
      });
    return (): void => controller.abort();
  }, [apiKey, ticket]);

  const renderBody = (): ReactElement => {
    if (!apiKey) return <EmptyState>Add your Linear API key in the plugin settings to link branches to issues.</EmptyState>;
    if (!branch) return <EmptyState>Waiting for the workspace branch…</EmptyState>;
    if (!ticket) return <EmptyState>{`No Linear ticket found in branch "${branch}".`}</EmptyState>;
    if (status === "loading") {
      return (
        <Flex align="center" justify="center" gap="2" p="5" style={{ flexGrow: 1 }}>
          <Spinner size="1" />
          <Text size="2" color="gray">
            Loading {ticket.identifier}…
          </Text>
        </Flex>
      );
    }
    if (status === "error") return <EmptyState>{error}</EmptyState>;
    if (!issue) return <EmptyState>{`${ticket.identifier} not found in Linear.`}</EmptyState>;
    return <IssueCard issue={issue} />;
  };

  return (
    <Flex direction="column" height="100%">
      <PanelHeader title="Linear" />
      {renderBody()}
    </Flex>
  );
};

const LinearSettings = (): ReactElement => {
  const [apiKey, setApiKey] = usePluginSetting("apiKey");
  return (
    <Flex direction="column" gap="2" style={{ maxWidth: 460 }}>
      <Text size="1" color="gray">
        Personal API key from Linear → Settings → Security &amp; access → Personal API keys. Stored locally in this
        browser only.
      </Text>
      <TextField.Root
        type="password"
        placeholder="lin_api_..."
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
      />
    </Flex>
  );
};

// `activate` is the plugin entry point. The host calls it once after loading
// the bundle; the returned function disposes the contributions on unload.
export default function activate(api: {
  registerPanel: (panel: {
    id: string;
    displayName: string;
    description: string;
    icon: typeof Hash;
    defaultZone: "top-left" | "bottom-left" | "bottom" | "top-right" | "bottom-right";
    defaultShortcut: string;
    component: () => ReactElement;
  }) => () => void;
  registerSettings: (component: () => ReactElement) => () => void;
}): () => void {
  const disposePanel = api.registerPanel({
    id: "linear-issue",
    displayName: "Linear",
    description: "Show the Linear issue linked to the workspace branch",
    icon: Hash,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: LinearPanel,
  });
  const disposeSettings = api.registerSettings(LinearSettings);
  return (): void => {
    disposePanel();
    disposeSettings();
  };
}
