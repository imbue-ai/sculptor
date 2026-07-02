import { Badge, Box, Flex, Text } from "@radix-ui/themes";
import type { ToolCallView } from "@sculptor/plugin-sdk";
import { Circle, CircleAlert, CircleCheck } from "lucide-react";
import type { ReactElement } from "react";

import { parseWorkflowInput, type ParsedWorkflow } from "./parseWorkflow.ts";

/**
 * The popover body for a `Workflow` tool call. The host renders the plugin's
 * summary line above this in the popover header, so the body owns everything
 * below it: the workflow's description, its phase checklist, and — once the
 * call finishes — the result text.
 *
 * While the call is running the phases are shown as a pending checklist. On
 * completion the result text (the workflow's return value) is shown, tinted for
 * errors. Input that the parser doesn't recognize (only possible for a
 * result-only block, since `canRender` gates the rest) still renders the result.
 */
export const WorkflowBody = ({ call }: { call: ToolCallView }): ReactElement => {
  const parsed = parseWorkflowInput(call.input);
  const isRunning = call.status === "running";

  return (
    <Flex direction="column" gap="3" p="1">
      {parsed !== null && <WorkflowDetails workflow={parsed} isRunning={isRunning} />}
      {call.result !== null && <WorkflowResult text={call.result.text} isError={call.result.isError} />}
    </Flex>
  );
};

/** The static description + phase checklist recovered from the workflow input. */
const WorkflowDetails = ({ workflow, isRunning }: { workflow: ParsedWorkflow; isRunning: boolean }): ReactElement => (
  <Flex direction="column" gap="3">
    {workflow.description !== undefined && (
      <Text size="2" color="gray">
        {workflow.description}
      </Text>
    )}

    {workflow.source === "scriptPath" && (
      <Text size="1" color="gray" style={{ fontFamily: "var(--code-font-family)" }}>
        {workflow.scriptPath}
      </Text>
    )}

    {workflow.phases.length > 0 && (
      <Flex direction="column" gap="1" asChild>
        <ol style={{ margin: 0, padding: 0, listStyle: "none" }}>
          {workflow.phases.map((phase, index) => (
            <PhaseRow key={index} title={phase.title} detail={phase.detail} isRunning={isRunning} />
          ))}
        </ol>
      </Flex>
    )}
  </Flex>
);

/**
 * One phase of the checklist. Phases carry no per-phase progress from the tool,
 * so a running workflow shows every phase as pending and a finished one shows
 * them settled; the row is intentionally status-agnostic beyond that.
 */
const PhaseRow = ({
  title,
  detail,
  isRunning,
}: {
  title: string;
  detail: string | undefined;
  isRunning: boolean;
}): ReactElement => (
  <Flex asChild align="start" gap="2" py="1">
    <li>
      <Box style={{ color: "var(--gray-9)", lineHeight: 0, paddingTop: "var(--space-1)" }}>
        {isRunning ? <Circle size={14} /> : <CircleCheck size={14} />}
      </Box>
      <Flex direction="column" gap="1">
        <Text size="2">{title}</Text>
        {detail !== undefined && (
          <Text size="1" color="gray">
            {detail}
          </Text>
        )}
      </Flex>
    </li>
  </Flex>
);

/** The workflow's return value, tinted red when the run reported an error. */
const WorkflowResult = ({ text, isError }: { text: string; isError: boolean }): ReactElement => (
  <Flex direction="column" gap="2">
    <Flex align="center" gap="2">
      {isError ? (
        <CircleAlert size={14} style={{ color: "var(--red-11)" }} />
      ) : (
        <CircleCheck size={14} style={{ color: "var(--green-11)" }} />
      )}
      <Badge size="1" color={isError ? "red" : "green"} variant="soft">
        {isError ? "Failed" : "Result"}
      </Badge>
    </Flex>
    <Box
      style={{
        maxHeight: "20rem",
        overflow: "auto",
        borderRadius: "var(--radius-2)",
        padding: "var(--space-2)",
        backgroundColor: isError ? "var(--red-a2)" : "var(--gray-a2)",
      }}
    >
      <Text
        size="1"
        style={{
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          fontFamily: "var(--code-font-family)",
          color: isError ? "var(--red-11)" : "var(--gray-12)",
        }}
      >
        {text}
      </Text>
    </Box>
  </Flex>
);
