/**
 * Sculptor background-task extension.
 *
 * Registers a single `background` tool that starts a shell command in the
 * background: the tool returns IMMEDIATELY (the agent keeps control; the turn
 * does not block on the command), and the command keeps running detached. When
 * it finishes, the extension reports completion out-of-band via `ctx.ui.notify`
 * carrying a STRUCTURED, versioned payload that the Sculptor adapter maps onto
 * the harness-agnostic `BackgroundTaskStarted`/`BackgroundTaskNotification`
 * contracts.
 *
 * Lifecycle:
 * - START: the tool's result `details` carry `{ v, task }` with the task's id,
 *   the launching tool-call id, and the child's process-group id (`pgid`). The
 *   adapter emits `BackgroundTaskStarted` and records the pgid so Sculptor can
 *   cancel the child on interrupt/stop by signalling that group INSIDE the
 *   environment (the extension API has no abort hook for detached work, so the
 *   parent tool's `signal` only covers the brief pre-return window).
 * - COMPLETION: a fire-and-forget `notify` carrying
 *   `{ "<MARKER>": { v, taskId, toolCallId, status, exitCode, summary,
 *   durationMs } }`. The adapter parses the marker and emits
 *   `BackgroundTaskNotification` (clearing the pending id and surfacing the
 *   summary).
 * - CLEANUP (no orphans): every live child is tracked and killed on
 *   `session_shutdown` (fires on quit / SIGTERM / reload / new / resume / fork),
 *   complementing the per-task in-environment `kill` Sculptor issues on
 *   interrupt and `isolate_process_group` on the pi process.
 *
 * Each child is spawned `detached` so it leads its OWN process group: Sculptor
 * can SIGTERM just that group (negative pgid) on a mid-flight interrupt without
 * touching the pi process.
 *
 * Pinned with the pi binary as one immutable unit (PI_VERSION_RANGE in
 * `dependency_management_service`). NOT user-visible or user-configurable, loaded
 * explicitly via `-e` under `--no-extensions` (no discovery). The child inherits
 * the parent process's environment, so no secret is plumbed or embedded here, and
 * the tool emits no telemetry.
 *
 * Wire contract shared with the Python side (`sculptor/agents/pi_agent/
 * background.py` and `tool_rendering.py`): the tool NAME, the payload VERSION,
 * the notify MARKER key, and the field names below MUST match the constants
 * there. Changing one means editing both files in the same change.
 */

import { spawn } from "node:child_process";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

// MUST match tool_rendering.py: BACKGROUND_TOOL_NAME.
const BACKGROUND_TOOL_NAME = "background";
// MUST match background.py: BACKGROUND_PAYLOAD_VERSION.
const BACKGROUND_PAYLOAD_VERSION = 1;
// MUST match background.py: BACKGROUND_NOTIFY_MARKER. The top-level key under
// which the completion payload rides the `notify` message string.
const BACKGROUND_NOTIFY_MARKER = "sculptorBackgroundTask";

// Cap the summary so the (single) notify message stays small.
const MAX_SUMMARY_BYTES = 8 * 1024;
// SIGTERM, then SIGKILL after this if the child ignores it.
const KILL_ESCALATION_MS = 3000;

interface LiveTask {
	taskId: string;
	toolCallId: string;
	label: string;
	command: string;
	pgid: number;
	kill: () => void;
}

// All in-flight children, keyed by taskId, so `session_shutdown` can reap them.
const liveTasks = new Map<string, LiveTask>();

// The session-scoped context captured at session_start. The completion `notify`
// fires from a DETACHED callback after the tool returned, so it uses the session
// ctx (not the per-tool ctx, whose lifetime ends with the tool call).
let sessionCtx: ExtensionContext | undefined;

function truncateSummary(text: string): string {
	if (Buffer.byteLength(text, "utf8") <= MAX_SUMMARY_BYTES) return text;
	let cut = text.slice(0, MAX_SUMMARY_BYTES);
	while (Buffer.byteLength(cut, "utf8") > MAX_SUMMARY_BYTES) cut = cut.slice(0, -1);
	return `${cut}\n[truncated]`;
}

export default function sculptorBackgroundExtension(pi: ExtensionAPI): void {
	pi.on("session_start", async (_event, ctx) => {
		sessionCtx = ctx;
	});

	// No orphans: kill every still-running child when the session tears down
	// (quit / SIGTERM / reload / new / resume / fork). This is the shutdown
	// guarantee; mid-flight interrupts are handled Sculptor-side by signalling
	// the child's process group in the environment.
	pi.on("session_shutdown", async (_event, _ctx) => {
		for (const task of liveTasks.values()) task.kill();
		liveTasks.clear();
	});

	pi.registerTool({
		name: BACKGROUND_TOOL_NAME,
		label: "Background task",
		description:
			"Run a shell command in the BACKGROUND and return immediately. Use this for a " +
			"long-running command (build, test suite, server, watch) you do not want to block " +
			"on: you keep working while it runs, and you are notified when it completes. Provide " +
			"`command` (the shell command) and an optional short `label`.",
		promptSnippet: "Run a shell command in the background",
		promptGuidelines: [
			`Use ${BACKGROUND_TOOL_NAME} to start a long-running command without blocking; you are notified on completion.`,
		],
		parameters: Type.Object({
			command: Type.String({ description: "The shell command to run in the background." }),
			label: Type.Optional(Type.String({ description: "A short label for this background task." })),
		}),
		async execute(toolCallId, params, signal, _onUpdate, _ctx) {
			const command = typeof params.command === "string" ? params.command : "";
			const label = (typeof params.label === "string" && params.label) || "background";
			if (!command.trim()) {
				return {
					content: [{ type: "text", text: "No command provided. Pass a non-empty `command`." }],
					details: { v: BACKGROUND_PAYLOAD_VERSION, task: null },
				};
			}

			const taskId = `bgt_${toolCallId}`;
			// `detached: true` puts the child in its OWN process group (pgid ===
			// child.pid) so Sculptor can SIGTERM just this group on interrupt
			// without touching pi. stdout/stderr are captured for the summary.
			const child = spawn("bash", ["-c", command], {
				detached: true,
				shell: false,
				stdio: ["ignore", "pipe", "pipe"],
			});
			const pgid = child.pid ?? -1;

			let output = "";
			let settled = false;
			const appendOutput = (data: Buffer) => {
				if (Buffer.byteLength(output, "utf8") < MAX_SUMMARY_BYTES) output += data.toString();
			};
			child.stdout?.on("data", appendOutput);
			child.stderr?.on("data", appendOutput);

			const start = Date.now();
			// Signal the child's whole process group (negative pgid) so any grandchild
			// it spawned (a shell pipeline, a server) dies too; fall back to the bare
			// process when no pgid is known.
			const kill = () => {
				try {
					if (pgid > 0) process.kill(-pgid, "SIGTERM");
					else child.kill("SIGTERM");
				} catch {
					/* already gone */
				}
				setTimeout(() => {
					try {
						if (pgid > 0) process.kill(-pgid, "SIGKILL");
						else if (!child.killed) child.kill("SIGKILL");
					} catch {
						/* already gone */
					}
				}, KILL_ESCALATION_MS);
			};

			const finish = (status: "completed" | "failed", exitCode: number | null) => {
				if (settled) return;
				settled = true;
				liveTasks.delete(taskId);
				const summary = truncateSummary(output.trim());
				// Out-of-band completion: a fire-and-forget notify carrying the
				// structured marker. Sculptor's adapter maps it onto
				// BackgroundTaskNotification (background.py / agent_wrapper).
				try {
					sessionCtx?.ui.notify(
						JSON.stringify({
							[BACKGROUND_NOTIFY_MARKER]: {
								v: BACKGROUND_PAYLOAD_VERSION,
								taskId,
								toolCallId,
								status,
								exitCode,
								summary,
								durationMs: Date.now() - start,
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
						`Your background task (${label}) finished: ${status}${exitCode === null ? "" : ` (exit ${exitCode})`}.`,
						{ deliverAs: "followUp" },
					);
				} catch {
					/* session torn down; nothing to deliver */
				}
			};

			child.on("close", (code) => finish(code === 0 ? "completed" : "failed", code));
			child.on("error", () => finish("failed", null));

			liveTasks.set(taskId, { taskId, toolCallId, label, command, pgid, kill });

			// The parent tool's signal only fires while execute is pending — i.e.
			// the brief window before this returns. After that the child is detached
			// and is cancelled Sculptor-side (in-env kill) or on session_shutdown.
			if (signal) {
				if (signal.aborted) kill();
				else signal.addEventListener("abort", kill, { once: true });
			}

			// Return immediately: the agent keeps control; the turn does not block.
			return {
				content: [{ type: "text", text: `Started background task ${label} (pid ${pgid}): ${command}` }],
				details: {
					v: BACKGROUND_PAYLOAD_VERSION,
					task: { taskId, toolCallId, label, command, pgid, status: "running" },
				},
			};
		},
	});
}
