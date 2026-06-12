# Task 9.1: Image input + file attachments (bundle) — `supports_image_input`, `supports_file_attachments`

## Goal

Files and images attached in a pi workspace reach the agent: images
travel as base64 on the `prompt` command, non-image attachments as file
paths pi reads with its own tools — and BOTH flags flip `True`. A
bundled tranche (shared prompt-assembly plumbing, REQ-PROC-4); each flag
still satisfies its own REQ-CAP individually. Feasibility verdicts both
**(i) Sculptor-side only** (`feasibility.md` §9–§10): `prompt.images[]`
works (model answered "Blue" to a blue PNG), bad images fail **loud**
(API 400 → `stopReason:"error"` → standard failed turn), and
attachments-by-path ride pi's `read` tool exactly as
`supports_file_references` (already `True`) proves.

## Requirements addressed

REQ-CAP-IMAGE-INPUT, REQ-CAP-FILE-ATTACHMENTS; REQ-CAP-ALL-1..7;
REQ-TEST-1/2/4.

## Background

The harness-agnostic transport already exists: the frontend uploads
files to `POST /api/v1/upload-file` (`app.py` ~3639; stored under the
uploads dir with uuid names) and sends the ids in
`SendMessageRequest.files` → `ChatInputUserMessage.files` (paths). pi's
prompt assembly currently sends `message.text` ONLY — `files` is
silently dropped (`PiAgent._process_message_queue` sends
`{"type":"prompt","message":message.text}`).

Claude's pattern to mirror: `_maybe_save_files_to_environment`
(`claude_code_sdk/process_manager.py:551-573`) resolves each entry
(absolute path, or `get_internal_folder()/uploads/<id>`), copies it into
`environment.get_attachments_path()`, and passes the resulting paths to
the prompt-instructions builder (`get_user_instructions(message=...,
file_paths=...)` — read it for the exact presentation wording).

The base tranche (PR #54) landed the gates: image surfaces (the
`+`-menu Images row, toolbar upload, paste path) and the attachments
gate read `useTaskSupportsImageInput` / `useTaskSupportsFileAttachments`
(`ChatInput.tsx:155-156`), with picker-row suppression as the fallback
treatment; attachments are AND-gated with model capabilities
(`canAttachFiles = modelCapabilities.supportsFileAttachments &&
canHarnessAttachFiles`, `ChatInput.tsx` ~169) —
`getModelCapabilities` defaults `supportsFileAttachments: true` for
unknown models (`modelCapabilities.ts:76-84`), so pi's model entries
(not in the Claude-keyed map) resolve permissive. The uploads gating
test is `test_chat_remains_usable_when_uploads_gated`
(`test_pi_capability_gating.py:132`).

Locked posture (architecture §4.11 + the requirements Q&A): the flag is
harness-level "pi can carry images"; when an image can't be processed,
the turn fails **loud** through the standard failed-turn path — no
silent drop (verified), no per-model gating this cycle — with a code
comment at the assembly site marking that per-model gating should hoist
later (the `modelCapabilities.ts` pattern is the named target).

Wire facts (`feasibility.md` §9): `ImageContent` =
`{"type":"image","data":"<base64>","mimeType":"image/png"}` (et al);
the image block appears in the user message pi builds; all 24 models
the configured provider returns are multimodal; JSONL framing imposes no
documented payload cap — practical limits are the model API's, surfaced
as the same loud error. Large files: pi's `read` streams with
`details.truncation`/`fullOutputPath` (§2) — prefer the path route for
anything that isn't genuinely an image the model must SEE.

## Files to modify/create

- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` — prompt
  assembly in `_process_message_queue`:
  1. Mirror `_maybe_save_files_to_environment` (same resolution rules,
     same destination `environment.get_attachments_path()`); share or
     adapt rather than fork-drift if a clean extraction exists.
  2. Split saved paths: image files (sniff by extension/magic — match
     the upload validation's notion of image from
     `FileUploadUtils.ts`/the upload endpoint rather than inventing one)
     → read bytes, base64, append to the `prompt` command's `images[]`
     with the right `mimeType`; non-images → present the paths in the
     prompt text the way Claude's `get_user_instructions` presents
     `file_paths`.
  3. The hoist-later comment: at the images[] assembly site, a comment
     stating model-capability gating is deliberately absent this cycle
     and where it should hoist (per-model gating à la
     `modelCapabilities.ts`).
- `sculptor/sculptor/agents/pi_agent/harness.py` — flip BOTH
  `supports_image_input=True` and `supports_file_attachments=True`;
  update stance comments.
- `sculptor/sculptor/agents/pi_agent/harness_test.py`,
  `agent_wrapper_test.py` — stances + assembly units.
- `sculptor/sculptor/testing/fake_pi.py` — accept and surface
  `prompt.images[]` (e.g. a directive-visible echo of received image
  count/mimeTypes so tests can assert delivery without a model).
- `sculptor/tests/integration/frontend/test_pi_capability_gating.py` —
  flip the uploads test's pi branch: attaching now works (image entries
  present, attachment delivered); keep the Claude branch identical.
- **Create** `sculptor/tests/integration/real_pi/test_image_input.py`
  (mirror of the probe: small valid PNG of a solid color → ask the
  color → assert answer) and
  `sculptor/tests/integration/real_pi/test_file_attachments.py` (attach
  a small text file with a sentinel → ask for the sentinel).

## Implementation details

1. Image set: match the upload pipeline's accepted image types (the
   frontend validates magic bytes/extension — `FileUploadUtils.ts`);
   anything the pipeline calls an image goes to `images[]`, everything
   else is a path attachment. One shared predicate, unit-tested.
2. Encoding: read bytes from the saved attachment path (NOT the upload
   dir — the copy into the environment is the contract), base64 without
   wrapping, correct `mimeType` per type.
3. Failure surface: a pi `response success:false` or in-turn
   `stopReason:"error"` from an unprocessable image already routes
   through the failed-turn path (PR #54's dispatcher) — add a unit
   fixture proving an image-triggered error message reaches the user
   visibly (the no-silent-drop bar, REQ-CAP-IMAGE-INPUT).
4. Empty/missing files: skip-with-warning exactly as Claude's
   `_maybe_save_files_to_environment` does (FileNotFoundError branch).
5. Frontend: no new code expected — suppressed surfaces flip live with
   the flags. Verify the paste path (`Editor.tsx` ~230) routes images
   for pi now.

## Testing suggestions

- Unit: predicate (image vs not); assembly (images[] populated, paths in
  prompt text, both together, neither); missing-file skip; failure
  surface fixture.
- Integration (fake_pi): attach image + text file in a pi workspace →
  fake_pi observes one image and one path; uploads gating test flipped;
  paste path delivers under pi.
- Real: the two new `real_pi` tests above (mirror
  `real_claude`-equivalent coverage where it exists; note shape
  divergences per REQ-TEST-1). Full `just test-real-pi` green at merge.

## Gotchas

- Don't double-deliver images (as BOTH `images[]` and a path) — the
  split is exclusive.
- Pasted images flow through the same `files` field as picked ones
  (`Editor.tsx`/`onFilesChange` unified pipeline) — no separate paste
  plumbing backend-side.
- Base64 inflates ~33%: a multi-MB screenshot is a multi-MB stdin line.
  No artificial cap this cycle (the model API errors loud), but log the
  encoded size at debug for triage.
- `getModelCapabilities` AND-gate: pi models resolve to the permissive
  default today — if that map ever gains pi entries, the AND could
  silently re-gate attachments; mention in the MR, don't fix
  preemptively.
- Tranche conventions: own workspace on
  `danver/pi-capabilities-attachments` rooted at current `origin/main`
  (≥ `99cbc0d`), MR → `main`; `just rebuild` first; commit rules
  (`just format`/`check`/`test-unit`, trailer
  `Co-authored-by: Sculptor <sculptor@imbue.com>`); integration tests via
  the repo's integration-test skill; evidence bundle in the MR
  (deterministic gates, FULL `just test-real-pi`, real-claude rerun — ask
  Danver if prerequisites are missing; ticked checklist); PR
  world-readable ending `(Sent by Claude)`; announce per
  post-mr-to-slack; pause for Danver before any deferral (REQ-INV-6).

## Verification checklist

- [ ] An attached text file's sentinel is usable by pi that turn; an
      attached/pasted image is genuinely SEEN (color test) on a real
      model.
- [ ] Unprocessable image → visible failed turn (no silent drop);
      hoist-later comment present at the assembly site.
- [ ] Both flags `True`; stance tests updated; image/attachment
      CAPABILITY-GAP markers (`MentionPickerList.tsx:143`,
      `Editor.tsx:230` region) resolved; uploads gating test flipped.
- [ ] Integration tests: flipped `test_pi_capability_gating.py` uploads
      test, `test_pi_basic.py`, `test_minimum_interface_conformance.py`;
      new `real_pi/test_image_input.py` +
      `real_pi/test_file_attachments.py`; full `real_pi/` green at merge.
