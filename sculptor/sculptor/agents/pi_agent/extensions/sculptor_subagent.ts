/**
 * Sculptor sub-agent extension.
 *
 * Gives a pi (`--mode rpc`) agent the sub-agent capability Sculptor exposes for
 * Claude. Registers a single `subagent` tool that delegates work to child
 * agents, each running as its own isolated `pi` process (single task, or a
 * capped parallel batch). It streams a STRUCTURED, versioned per-child lifecycle
 * payload under the tool result's `details` so the Sculptor adapter can render
 * each child's activity as nested, attributed blocks (a parent entry with the
 * child's own tool calls and text grouped beneath it) — Claude-parity sub-agent
 * rendering.
 *
 * `partialResult` is ACCUMULATED, not a delta, so every `onUpdate` re-sends the
 * full `{ v, children }` snapshot; the Python adapter re-parses it idempotently
 * (`subagent.py`) and emits each child exactly once.
 *
 * Pinned with the pi binary as one immutable unit (PI_VERSION_RANGE in
 * `dependency_management_service`). It is NOT user-visible or user-configurable
 * and is loaded explicitly via `-e` under `--no-extensions` (no discovery).
 * Children inherit the parent process's environment — including its API key — so
 * no secret is plumbed or embedded here, and the tool emits no telemetry. Child
 * processes run `--no-session` so they never pollute Sculptor's managed pi
 * session directory.
 *
 * Wire contract shared with the Python side
 * (`sculptor/agents/pi_agent/subagent.py` and `tool_rendering.py`): the tool
 * NAME and the payload VERSION + field names below MUST match the constants
 * there. Changing one means editing both files in the same change.
 */

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

// MUST match tool_rendering.py: SUBAGENT_TOOL_NAME.
const SUBAGENT_TOOL_NAME = "subagent";
// MUST match subagent.py: SUBAGENT_PAYLOAD_VERSION.
const SUBAGENT_PAYLOAD_VERSION = 1;

// Caps so a runaway prompt cannot spawn unbounded child processes.
const MAX_TASKS = 8;
const MAX_CONCURRENCY = 4;
// Per-child bounds so the accumulated (re-sent-every-update) payload stays bounded.
const MAX_EVENTS_PER_CHILD = 200;
const MAX_EVENT_TEXT_BYTES = 8 * 1024;

type ChildEventKind = "text" | "tool_call" | "tool_result";

interface ChildEvent {
	seq: number;
	kind: ChildEventKind;
	text?: string;
	toolCallId?: string;
	toolName?: string;
	args?: Record<string, unknown>;
	isError?: boolean;
}

interface ChildState {
	childId: string;
	label: string;
	task: string;
	status: "running" | "done" | "error";
	stopReason?: string;
	exitCode?: number;
	events: ChildEvent[];
}

interface SubagentPayload {
	v: number;
	children: ChildState[];
}

function truncateText(text: string): string {
	if (Buffer.byteLength(text, "utf8") <= MAX_EVENT_TEXT_BYTES) return text;
	let cut = text.slice(0, MAX_EVENT_TEXT_BYTES);
	while (Buffer.byteLength(cut, "utf8") > MAX_EVENT_TEXT_BYTES) cut = cut.slice(0, -1);
	return `${cut}\n[truncated]`;
}

function resultText(result: any): string {
	// pi tool results ride as { content: [{type:"text", text}], details }; flatten
	// the text parts, else stringify.
	if (result && Array.isArray(result.content)) {
		const parts = result.content
			.filter((b: any) => b && b.type === "text" && typeof b.text === "string")
			.map((b: any) => b.text);
		if (parts.length > 0) return parts.join("");
	}
	if (typeof result === "string") return result;
	try {
		return JSON.stringify(result);
	} catch {
		return String(result);
	}
}

// Reuse the parent's exact pi runtime/binary for children (the managed
// standalone binary, or a dev `node cli.js`), rather than a bare PATH `pi`
// which may be absent or a different version.
function getPiInvocation(args: string[]): { command: string; args: string[] } {
	const currentScript = process.argv[1];
	const isBunVirtualScript = currentScript?.startsWith("/$bunfs/root/");
	if (currentScript && !isBunVirtualScript && fs.existsSync(currentScript)) {
		return { command: process.execPath, args: [currentScript, ...args] };
	}
	const execName = path.basename(process.execPath).toLowerCase();
	const isGenericRuntime = /^(node|bun)(\.exe)?$/.test(execName);
	if (!isGenericRuntime) {
		return { command: process.execPath, args };
	}
	return { command: "pi", args };
}

async function mapWithConcurrencyLimit<TIn, TOut>(
	items: TIn[],
	concurrency: number,
	fn: (item: TIn, index: number) => Promise<TOut>,
): Promise<TOut[]> {
	if (items.length === 0) return [];
	const limit = Math.max(1, Math.min(concurrency, items.length));
	const results: TOut[] = new Array(items.length);
	let nextIndex = 0;
	const workers = new Array(limit).fill(null).map(async () => {
		while (true) {
			const current = nextIndex++;
			if (current >= items.length) return;
			results[current] = await fn(items[current], current);
		}
	});
	await Promise.all(workers);
	return results;
}

// Run one child to completion, mutating `child` as its events arrive and
// invoking `emit` (the accumulated snapshot) on every change.
async function runChild(child: ChildState, signal: AbortSignal | undefined, emit: () => void): Promise<void> {
	let seq = 0;
	const push = (event: Omit<ChildEvent, "seq">) => {
		if (child.events.length >= MAX_EVENTS_PER_CHILD) return;
		child.events.push({ seq: seq++, ...event });
		emit();
	};

	const args = ["--mode", "json", "-p", "--no-session", `Task: ${child.task}`];
	const invocation = getPiInvocation(args);
	let wasAborted = false;

	const exitCode = await new Promise<number>((resolve) => {
		const proc = spawn(invocation.command, invocation.args, { shell: false, stdio: ["ignore", "pipe", "pipe"] });
		let buffer = "";
		const processLine = (line: string) => {
			if (!line.trim()) return;
			let event: any;
			try {
				event = JSON.parse(line);
			} catch {
				return;
			}
			// Tool calls + their results come from the tool-execution lane (clean
			// {toolCallId, toolName, args} / {result, isError}); assistant TEXT
			// comes from message_end. The issuing message's toolCall content block
			// is deliberately NOT captured here so a call is recorded once.
			if (event.type === "tool_execution_start") {
				push({
					kind: "tool_call",
					toolCallId: String(event.toolCallId ?? ""),
					toolName: String(event.toolName ?? ""),
					args: typeof event.args === "object" && event.args ? event.args : {},
				});
			} else if (event.type === "tool_execution_end") {
				push({
					kind: "tool_result",
					toolCallId: String(event.toolCallId ?? ""),
					toolName: String(event.toolName ?? ""),
					text: truncateText(resultText(event.result)),
					isError: Boolean(event.isError),
				});
			} else if (event.type === "message_end" && event.message?.role === "assistant") {
				for (const part of event.message.content ?? []) {
					if (part?.type === "text" && typeof part.text === "string" && part.text) {
						push({ kind: "text", text: truncateText(part.text) });
					}
				}
				if (event.message.stopReason) child.stopReason = String(event.message.stopReason);
			}
		};
		proc.stdout.on("data", (data) => {
			buffer += data.toString();
			const lines = buffer.split("\n");
			buffer = lines.pop() || "";
			for (const line of lines) processLine(line);
		});
		proc.on("close", (code) => {
			if (buffer.trim()) processLine(buffer);
			resolve(code ?? 0);
		});
		proc.on("error", () => resolve(1));
		// Parent abort (Sculptor's Stop → pi `abort` → this AbortSignal) kills the
		// child process tree so no orphan `pi` survives the interrupt.
		if (signal) {
			const kill = () => {
				wasAborted = true;
				proc.kill("SIGTERM");
				setTimeout(() => {
					if (!proc.killed) proc.kill("SIGKILL");
				}, 3000);
			};
			if (signal.aborted) kill();
			else signal.addEventListener("abort", kill, { once: true });
		}
	});

	child.exitCode = exitCode;
	if (wasAborted || child.stopReason === "aborted") {
		child.status = "error";
		child.stopReason = child.stopReason || "aborted";
	} else if (exitCode !== 0 || child.stopReason === "error") {
		child.status = "error";
	} else {
		child.status = "done";
	}
	emit();
}

export default function sculptorSubagentExtension(pi: ExtensionAPI): void {
	pi.registerTool({
		name: SUBAGENT_TOOL_NAME,
		label: "Sub-agent",
		description:
			"Delegate a task to a sub-agent that runs in its own isolated context and " +
			"reports back when done. Provide a single `task`, or `tasks` (a list) to run " +
			"several sub-agents in parallel. Use this to parallelize independent work or " +
			"to keep a large investigation out of the main context.",
		promptSnippet: "Delegate a task to an isolated sub-agent",
		promptGuidelines: [
			`Use ${SUBAGENT_TOOL_NAME} to delegate a self-contained task (or several parallel tasks) to isolated sub-agents.`,
		],
		parameters: Type.Object({
			task: Type.Optional(Type.String({ description: "A single task to delegate to one sub-agent." })),
			tasks: Type.Optional(
				Type.Array(
					Type.Object({
						task: Type.String({ description: "The task for this sub-agent." }),
						label: Type.Optional(Type.String({ description: "A short label for this sub-agent." })),
					}),
					{ description: "Several tasks to run as parallel sub-agents." },
				),
			),
		}),
		async execute(_toolCallId, params, signal, onUpdate, _ctx) {
			const requested =
				Array.isArray(params.tasks) && params.tasks.length > 0
					? params.tasks.map((t, i) => ({ task: t.task, label: t.label || `subagent ${i + 1}` }))
					: typeof params.task === "string" && params.task
						? [{ task: params.task, label: "subagent" }]
						: [];

			if (requested.length === 0) {
				return {
					content: [{ type: "text", text: "No task provided. Pass `task` or a non-empty `tasks` list." }],
					details: { v: SUBAGENT_PAYLOAD_VERSION, children: [] } satisfies SubagentPayload,
				};
			}

			const capped = requested.slice(0, MAX_TASKS);
			const children: ChildState[] = capped.map((t, i) => ({
				childId: `c${i}`,
				label: t.label,
				task: t.task,
				status: "running",
				events: [],
			}));

			const snapshot = (): SubagentPayload => ({ v: SUBAGENT_PAYLOAD_VERSION, children });
			const summaryText = () => {
				const done = children.filter((c) => c.status === "done").length;
				const failed = children.filter((c) => c.status === "error").length;
				const running = children.filter((c) => c.status === "running").length;
				return `sub-agents: ${done} done, ${failed} failed, ${running} running (of ${children.length})`;
			};
			const emit = () => {
				onUpdate?.({ content: [{ type: "text", text: summaryText() }], details: snapshot() });
			};
			emit();

			await mapWithConcurrencyLimit(children, MAX_CONCURRENCY, async (child) => {
				await runChild(child, signal, emit);
			});

			return {
				content: [{ type: "text", text: summaryText() }],
				details: snapshot(),
			};
		},
	});
}
