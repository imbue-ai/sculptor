/**
 * Sculptor sub-agent extension (yield-early / async).
 *
 * Registers a single `subagent` tool that delegates work to child agents, each
 * running as its own isolated `pi` process (single task, or a capped batch). The
 * tool returns IMMEDIATELY (the agent keeps control; the turn does NOT block on
 * the children), and the children keep running detached. When the whole batch
 * finishes, the extension reports completion OUT-OF-BAND via `ctx.ui.notify`
 * carrying a STRUCTURED, versioned per-child payload the Sculptor adapter renders
 * as nested, attributed blocks (a parent `Agent` entry with each child's own tool
 * calls and text grouped beneath it).
 *
 * Lifecycle:
 * - START: the tool's result `details` carry `{ v, task }` with the task id, the
 *   launching tool-call id, every child's process-group id (`pgids`), and the
 *   child count. The adapter records the pgids (so Sculptor can SIGTERM the child
 *   groups INSIDE the environment on shutdown) and emits a started indicator. The
 *   launching turn then ends — the user keeps chatting while the children run.
 * - COMPLETION: a fire-and-forget `notify` carrying
 *   `{ "<MARKER>": { v, taskId, toolCallId, status, children } }`. The adapter
 *   parses the marker and surfaces each child nested under the parent, plus a
 *   completion notification that clears the started indicator.
 * - CLEANUP (no orphans): every live child is tracked and killed on
 *   `session_shutdown` (quit / SIGTERM / reload / new / resume / fork),
 *   complementing the per-task in-environment group `kill` Sculptor issues on
 *   shutdown.
 *
 * Each child is spawned `detached` so it leads its OWN process group: Sculptor
 * (and this extension) can SIGTERM just that group (negative pgid) without
 * touching the pi process or sibling children.
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
 * NAME, the payload VERSION, the notify MARKER key, and the field names below
 * MUST match the constants there. Changing one means editing both files in the
 * same change.
 */

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

// MUST match tool_rendering.py: SUBAGENT_TOOL_NAME.
const SUBAGENT_TOOL_NAME = "subagent";
// MUST match subagent.py: SUBAGENT_PAYLOAD_VERSION.
const SUBAGENT_PAYLOAD_VERSION = 1;
// MUST match subagent.py: SUBAGENT_NOTIFY_MARKER. The top-level key under which
// the completion payload rides the `notify` message string.
const SUBAGENT_NOTIFY_MARKER = "sculptorSubagentTask";

// Cap so a runaway prompt cannot spawn unbounded child processes. All children
// are spawned at once (detached) up to this cap; the cap is the resource bound.
const MAX_TASKS = 8;
// Per-child bounds so the accumulated completion payload stays bounded.
const MAX_EVENTS_PER_CHILD = 200;
const MAX_EVENT_TEXT_BYTES = 8 * 1024;
// SIGTERM, then SIGKILL after this if the child ignores it.
const KILL_ESCALATION_MS = 3000;

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

// One in-flight sub-agent batch, keyed by taskId, so `session_shutdown` can reap
// every child it spawned.
interface LiveTask {
	taskId: string;
	kill: () => void;
}

const liveTasks = new Map<string, LiveTask>();

// The session-scoped context captured at session_start. The completion `notify`
// fires from a DETACHED callback after the tool returned, so it uses the session
// ctx (not the per-tool ctx, whose lifetime ends with the tool call).
let sessionCtx: ExtensionContext | undefined;

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

// Kill a detached child's whole process group (negative pgid) so any grandchild
// it spawned dies too; fall back to the bare process when no pgid is known.
function killGroup(pgid: number, proc: ReturnType<typeof spawn>): void {
	const term = () => {
		try {
			if (pgid > 0) process.kill(-pgid, "SIGTERM");
			else proc.kill("SIGTERM");
		} catch {
			/* already gone */
		}
	};
	term();
	setTimeout(() => {
		try {
			if (pgid > 0) process.kill(-pgid, "SIGKILL");
			else if (!proc.killed) proc.kill("SIGKILL");
		} catch {
			/* already gone */
		}
	}, KILL_ESCALATION_MS);
}

// Spawn one child SYNCHRONOUSLY (so its pgid is known immediately for the launch
// payload), wiring its stdout into `child` as events arrive. Returns the pgid, a
// kill handle, and a promise that resolves when the child exits. No streaming
// callback: the agent has yielded, so events accumulate for the single
// completion `notify`.
function startChild(child: ChildState, signal: AbortSignal | undefined): {
	pgid: number;
	kill: () => void;
	done: Promise<void>;
} {
	let seq = 0;
	const push = (event: Omit<ChildEvent, "seq">) => {
		if (child.events.length >= MAX_EVENTS_PER_CHILD) return;
		child.events.push({ seq: seq++, ...event });
	};

	const args = ["--mode", "json", "-p", "--no-session", `Task: ${child.task}`];
	const invocation = getPiInvocation(args);
	// detached: the child leads its OWN process group so it (and any grandchild)
	// can be torn down via the negative pgid without touching pi.
	const proc = spawn(invocation.command, invocation.args, {
		detached: true,
		shell: false,
		stdio: ["ignore", "pipe", "pipe"],
	});
	const pgid = proc.pid ?? -1;
	let wasAborted = false;
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
		// {toolCallId, toolName, args} / {result, isError}); assistant TEXT comes
		// from message_end. The issuing message's toolCall content block is NOT
		// captured here, so a call is recorded once.
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

	proc.stdout?.on("data", (data) => {
		buffer += data.toString();
		const lines = buffer.split("\n");
		buffer = lines.pop() || "";
		for (const line of lines) processLine(line);
	});

	const kill = () => {
		wasAborted = true;
		killGroup(pgid, proc);
	};

	const done = new Promise<void>((resolve) => {
		proc.on("close", (code) => {
			if (buffer.trim()) processLine(buffer);
			child.exitCode = code ?? 0;
			if (wasAborted || child.stopReason === "aborted") {
				child.status = "error";
				child.stopReason = child.stopReason || "aborted";
			} else if ((code ?? 0) !== 0 || child.stopReason === "error") {
				child.status = "error";
			} else {
				child.status = "done";
			}
			resolve();
		});
		proc.on("error", () => {
			child.status = "error";
			child.exitCode = child.exitCode ?? 1;
			resolve();
		});
	});

	// The parent tool's signal only fires while execute is pending (the brief
	// pre-return window); after that the child is detached and reaped on
	// session_shutdown / by Sculptor's in-env group kill.
	if (signal) {
		if (signal.aborted) kill();
		else signal.addEventListener("abort", kill, { once: true });
	}

	return { pgid, kill, done };
}

export default function sculptorSubagentExtension(pi: ExtensionAPI): void {
	pi.on("session_start", async (_event, ctx) => {
		sessionCtx = ctx;
	});

	// No orphans: kill every still-running child when the session tears down.
	pi.on("session_shutdown", async (_event, _ctx) => {
		for (const task of liveTasks.values()) task.kill();
		liveTasks.clear();
	});

	pi.registerTool({
		name: SUBAGENT_TOOL_NAME,
		label: "Sub-agent",
		description:
			"Delegate a task to a sub-agent that runs in its own isolated context in the " +
			"BACKGROUND and reports back when done. Provide a single `task`, or `tasks` (a " +
			"list) to run several sub-agents in parallel. The call returns immediately — you " +
			"keep working while the sub-agents run, and you are notified when they finish. " +
			"Use this to parallelize independent work or to keep a large investigation out of " +
			"the main context.",
		promptSnippet: "Delegate a task to an isolated background sub-agent",
		promptGuidelines: [
			`Use ${SUBAGENT_TOOL_NAME} to delegate a self-contained task (or several parallel tasks) to isolated sub-agents; the call returns immediately and you are notified on completion.`,
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
		async execute(toolCallId, params, signal, _onUpdate, _ctx) {
			const requested =
				Array.isArray(params.tasks) && params.tasks.length > 0
					? params.tasks.map((t, i) => ({ task: t.task, label: t.label || `subagent ${i + 1}` }))
					: typeof params.task === "string" && params.task
						? [{ task: params.task, label: "subagent" }]
						: [];

			if (requested.length === 0) {
				return {
					content: [{ type: "text", text: "No task provided. Pass `task` or a non-empty `tasks` list." }],
					details: { v: SUBAGENT_PAYLOAD_VERSION, task: null },
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

			const taskId = `sat_${toolCallId}`;
			const label = children.length === 1 ? children[0].label : `${children.length} sub-agents`;

			// Spawn every child synchronously (detached) so all pgids are known NOW
			// and reported in the launch payload; their output is processed and the
			// batch is awaited asynchronously, after this returns.
			const handles = children.map((child) => startChild(child, signal));
			const pgids = handles.map((h) => h.pgid).filter((p) => p > 0);
			const killAll = () => {
				for (const h of handles) h.kill();
			};
			liveTasks.set(taskId, { taskId, kill: killAll });

			// Out-of-band completion: when the whole batch settles, fire a single
			// fire-and-forget notify carrying the full per-child snapshot. The turn
			// has already ended, so Sculptor surfaces this via its idle-drain.
			void Promise.all(handles.map((h) => h.done)).then(() => {
				liveTasks.delete(taskId);
				const status = children.some((c) => c.status === "error") ? "failed" : "completed";
				const done = children.filter((c) => c.status === "done").length;
				const failed = children.filter((c) => c.status === "error").length;
				try {
					sessionCtx?.ui.notify(
						JSON.stringify({
							[SUBAGENT_NOTIFY_MARKER]: {
								v: SUBAGENT_PAYLOAD_VERSION,
								taskId,
								toolCallId,
								status,
								children,
							},
						}),
						status === "completed" ? "info" : "warning",
					);
				} catch {
					/* session torn down between completion and notify; nothing to surface */
				}
				// Wake the calling agent so it can react to the completion. sendUserMessage
				// triggers a turn when the agent is idle; deliverAs "followUp" queues it
				// behind an in-flight user turn instead of interrupting it.
				try {
					pi.sendUserMessage(
						`Your delegated sub-agent task (${label}) finished: ${status} — ${done}/${children.length} done, ${failed} failed.`,
						{ deliverAs: "followUp" },
					);
				} catch {
					/* session torn down; nothing to deliver */
				}
			});

			// Return immediately: the agent keeps control; the turn does not block.
			return {
				content: [
					{
						type: "text",
						text: `Started ${children.length} sub-agent(s): ${children.map((c) => c.label).join(", ")}`,
					},
				],
				details: {
					v: SUBAGENT_PAYLOAD_VERSION,
					task: { taskId, toolCallId, label, pgids, count: children.length, status: "running" },
				},
			};
		},
	});
}
