/**
 * Sculptor backchannel extension.
 *
 * Gives a pi (`--mode rpc`) agent the two interactive-backchannel surfaces
 * Sculptor already exposes for Claude — ask-user-question and plan mode —
 * by registering two tools whose `execute` opens a blocking pi dialog
 * (`ctx.ui.select` / `ctx.ui.input`). In RPC mode those dialogs surface as
 * `extension_ui_request` events that Sculptor maps onto its harness-agnostic
 * `AskUserQuestionAgentMessage` contract, and the user's answer is delivered
 * back as the matching `extension_ui_response`. With no `timeout` on the
 * dialog calls pi blocks indefinitely — exactly Sculptor's unbounded-wait
 * question model (the user may take as long as they like to answer).
 *
 * Pinned with the pi binary as one immutable unit (PI_VERSION_RANGE in
 * `dependency_management_service`). It is NOT user-visible or user-configurable
 * and is loaded explicitly via `-e` under `--no-extensions` (no discovery).
 * Re-validate against `examples/extensions/plan-mode` and the RPC extension-UI
 * protocol on any pi version bump. It embeds no secrets and emits no telemetry.
 *
 * Wire contract shared with the Python side
 * (`sculptor/agents/pi_agent/backchannel.py`): the two tool names and the
 * plan-approval dialog title below MUST match the constants there. Renaming
 * one means editing both files in the same change.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

// MUST match backchannel.py: ASK_USER_QUESTION_TOOL_NAME / EXIT_PLAN_MODE_TOOL_NAME.
const ASK_USER_QUESTION_TOOL_NAME = "ask_user_question";
const EXIT_PLAN_MODE_TOOL_NAME = "exit_plan_mode";

// Sentinel title the plan-approval dialog passes to ctx.ui.select. The
// ask-user-question and plan-approval dialogs both ride the same
// extension_ui_request{method:"select"} lane; Sculptor distinguishes them by
// this title (MUST match backchannel.py: PLAN_APPROVAL_DIALOG_TITLE).
const PLAN_APPROVAL_DIALOG_TITLE = "__sculptor_plan_approval__";

// The single option offered by the plan-approval dialog. Matches the label
// `make_plan_approval_question` puts on the canonical Sculptor plan question;
// a freeform answer (typed via the Sculptor "Revise" affordance) comes back as
// a value other than this and is treated as revision feedback.
const PLAN_APPROVE_ANSWER = "Approve plan";

export default function sculptorBackchannelExtension(pi: ExtensionAPI): void {
	pi.registerTool({
		name: ASK_USER_QUESTION_TOOL_NAME,
		label: "Ask User Question",
		description:
			"Ask the user a question and wait for their answer before continuing. " +
			"Provide `options` for a multiple-choice question, or omit them for a " +
			"free-form text answer. Use this for blocking decisions you need the " +
			"user to make mid-task; for rhetorical or non-blocking asides, just " +
			"write text instead.",
		promptSnippet: "Ask the user a blocking question and wait for their answer",
		promptGuidelines: [
			`Use ${ASK_USER_QUESTION_TOOL_NAME} when you need a decision from the user before you can proceed.`,
		],
		parameters: Type.Object({
			question: Type.String({ description: "The question to put to the user." }),
			options: Type.Optional(
				Type.Array(Type.String(), {
					description:
						"Multiple-choice options. Omit for a free-form text answer.",
				}),
			),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const options = params.options ?? [];
			const answer =
				options.length > 0
					? await ctx.ui.select(params.question, options)
					: await ctx.ui.input(params.question, "");
			if (answer === undefined) {
				return {
					content: [
						{
							type: "text",
							text: "The user dismissed the question without answering. Stop and wait for the user to respond.",
						},
					],
					details: { dismissed: true },
				};
			}
			return {
				content: [{ type: "text", text: `The user answered: ${answer}` }],
				details: { answer },
			};
		},
	});

	pi.registerTool({
		name: EXIT_PLAN_MODE_TOOL_NAME,
		label: "Exit Plan Mode",
		description:
			"Call this once your plan is ready, to present it to the user for " +
			"approval before you make any changes. Do not modify files until the " +
			"user approves. If the user requests revisions, refine the plan and " +
			"call this tool again.",
		promptSnippet: "Present the finished plan for user approval before making changes",
		promptGuidelines: [
			`Use ${EXIT_PLAN_MODE_TOOL_NAME} when you are in plan mode and your plan is ready for the user to approve.`,
		],
		parameters: Type.Object({
			plan: Type.Optional(
				Type.String({ description: "The plan to present, for the user to approve." }),
			),
		}),
		async execute(_toolCallId, _params, _signal, _onUpdate, ctx) {
			const choice = await ctx.ui.select(PLAN_APPROVAL_DIALOG_TITLE, [PLAN_APPROVE_ANSWER]);
			if (choice === undefined) {
				return {
					content: [
						{
							type: "text",
							text: "The user dismissed the plan. Stop and wait for further instructions; do not start implementing.",
						},
					],
					details: { dismissed: true },
				};
			}
			if (choice === PLAN_APPROVE_ANSWER) {
				return {
					content: [{ type: "text", text: "The user approved the plan. Proceed with implementing it." }],
					details: { approved: true },
				};
			}
			return {
				content: [
					{
						type: "text",
						text: `The user did not approve the plan and requests revisions: ${choice}`,
					},
				],
				details: { approved: false, feedback: choice },
			};
		},
	});
}
