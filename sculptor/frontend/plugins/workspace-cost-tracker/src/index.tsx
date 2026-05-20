import { Badge, Box, Flex, Text } from "@radix-ui/themes";
import {
  ArtifactType,
  PanelHeader,
  useTaskArtifact,
  useWorkspaceTasks,
  type CodingAgentTaskView,
  type UsageArtifact,
} from "@sculptor/plugin-sdk";
import { Coins } from "lucide-react";
import { useEffect, useState, type ReactElement } from "react";

const formatUsd = (n: number): string =>
  n >= 10 ? `$${n.toFixed(2)}` : `$${n.toFixed(4).replace(/0+$/, "").replace(/\.$/, "")}`;

const formatTokens = (n: number): string => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
};

type TaskUsageEntry = { cost: number; tokens: number } | null;

type TaskRowProps = {
  task: CodingAgentTaskView;
  onUsage: (taskId: string, usage: TaskUsageEntry) => void;
};

/**
 * One row per agent. Mounting this calls `useTaskArtifact` once, which the
 * SDK uses to trigger (and dedupe) the fetch. The row reports its loaded
 * usage to the parent via `onUsage` so totals can be computed without the
 * parent having to call N hooks in a loop.
 */
const TaskRow = ({ task, onUsage }: TaskRowProps): ReactElement => {
  const usage = useTaskArtifact(task.id, ArtifactType.USAGE);

  useEffect(() => {
    const entry: TaskUsageEntry = usage
      ? { cost: usage.costUsdInfo, tokens: usage.tokenInfo }
      : null;
    onUsage(task.id, entry);
    return (): void => onUsage(task.id, null);
  }, [task.id, usage, onUsage]);

  const label = task.title ?? task.titleOrSomethingLikeIt ?? task.id.slice(0, 8);
  const cost = usage?.costUsdInfo ?? 0;
  const tokens = usage?.tokenInfo ?? 0;
  const percentage = usage?.percentage;

  return (
    <Flex
      align="center"
      justify="between"
      gap="3"
      py="2"
      px="3"
      style={{ borderBottom: "1px solid var(--gray-4)" }}
    >
      <Flex direction="column" gap="1" style={{ minWidth: 0, flexGrow: 1 }}>
        <Text size="2" weight="medium" truncate>
          {label}
        </Text>
        <Flex gap="2" align="center">
          <Text size="1" color="gray">
            {formatTokens(tokens)} tokens
          </Text>
          {percentage !== undefined && (
            <Badge size="1" color={percentage > 80 ? "amber" : "gray"} variant="soft">
              {percentage.toFixed(0)}% context
            </Badge>
          )}
        </Flex>
      </Flex>
      <Text size="2" weight="medium">
        {usage ? formatUsd(cost) : "…"}
      </Text>
    </Flex>
  );
};

const WorkspaceCostPanel = (): ReactElement => {
  const tasks = useWorkspaceTasks();
  const [entries, setEntries] = useState<Record<string, TaskUsageEntry>>({});

  const handleUsage = (taskId: string, entry: TaskUsageEntry): void => {
    setEntries((prev) => {
      const prevEntry = prev[taskId];
      if (
        (prevEntry === null && entry === null) ||
        (prevEntry &&
          entry &&
          prevEntry.cost === entry.cost &&
          prevEntry.tokens === entry.tokens)
      ) {
        return prev;
      }
      return { ...prev, [taskId]: entry };
    });
  };

  if (!tasks) {
    return (
      <Flex direction="column" height="100%">
        <PanelHeader title="Usage" />
        <Flex align="center" justify="center" p="4">
          <Text size="2" color="gray">
            Loading agents…
          </Text>
        </Flex>
      </Flex>
    );
  }

  const totalCost = Object.values(entries).reduce((s, v) => s + (v?.cost ?? 0), 0);
  const totalTokens = Object.values(entries).reduce((s, v) => s + (v?.tokens ?? 0), 0);

  return (
    <Flex direction="column" height="100%">
      <PanelHeader title="Usage" />
      <Box
        p="3"
        style={{
          borderBottom: "1px solid var(--gray-5)",
          background: "var(--gray-2)",
        }}
      >
        <Flex justify="between" align="center">
          <Flex direction="column">
            <Text size="1" color="gray">
              Workspace total
            </Text>
            <Text size="4" weight="bold">
              {formatUsd(totalCost)}
            </Text>
          </Flex>
          <Flex direction="column" align="end">
            <Text size="1" color="gray">
              Tokens
            </Text>
            <Text size="2" weight="medium">
              {formatTokens(totalTokens)}
            </Text>
          </Flex>
        </Flex>
      </Box>
      <Box style={{ overflowY: "auto", flexGrow: 1 }}>
        {tasks.length === 0 ? (
          <Flex align="center" justify="center" p="4">
            <Text size="2" color="gray">
              No agents in this workspace yet
            </Text>
          </Flex>
        ) : (
          tasks.map((t) => <TaskRow key={t.id} task={t} onUsage={handleUsage} />)
        )}
      </Box>
    </Flex>
  );
};

// `activate` is the plugin's entry point. The host calls it once after
// loading the bundle, passing an API object. Returning a function makes
// it the disposer the host runs on unload.
export default function activate(api: {
  registerPanel: (panel: {
    id: string;
    displayName: string;
    description: string;
    icon: typeof Coins;
    defaultZone: "top-left" | "bottom-left" | "bottom" | "top-right" | "bottom-right";
    defaultShortcut: string;
    component: () => ReactElement;
  }) => () => void;
}): () => void {
  return api.registerPanel({
    id: "workspace-cost-tracker",
    displayName: "Usage",
    description: "Cost and tokens used by agents in this workspace",
    icon: Coins,
    defaultZone: "bottom-right",
    defaultShortcut: "",
    component: WorkspaceCostPanel,
  });
}
