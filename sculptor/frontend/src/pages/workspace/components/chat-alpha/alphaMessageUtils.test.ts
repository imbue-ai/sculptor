import { describe, expect, it } from "vitest";

import type { ChatMessage } from "~/api";

import { buildToolResultMap, mergeChatAndQueuedMessages, omitMessagesAlreadyInChat } from "./alphaMessageUtils.ts";

const makeMessage = (id: string): ChatMessage =>
  ({
    id,
    role: "USER",
    content: [{ type: "text", text: "test" }],
    approximateCreationTime: "2026-03-09T14:30:00.000Z",
  }) as unknown as ChatMessage;

describe("mergeChatAndQueuedMessages", () => {
  it("drops a queued message whose id already appears in the completed list", () => {
    // Repro: after a hard-kill restart the backend can briefly report the same
    // id in BOTH the completed and queued lists (see message_conversion.py).
    // Concatenating them blindly yields two entries with the same id -> a
    // duplicate React key that detaches virtualized rows and leaks them across
    // agents. The merge must keep the id exactly once, preferring the completed
    // (sent) copy.
    const sent = makeMessage("agm_dup");
    const queuedDuplicate = makeMessage("agm_dup");

    const merged = mergeChatAndQueuedMessages([sent], [queuedDuplicate]);

    expect(merged.map((message) => message.id)).toEqual(["agm_dup"]);
    expect(merged[0]).toBe(sent);
  });

  it("keeps genuinely distinct queued messages in order", () => {
    const sent = makeMessage("a");
    const queued = makeMessage("b");

    const merged = mergeChatAndQueuedMessages([sent], [queued]);

    expect(merged.map((message) => message.id)).toEqual(["a", "b"]);
  });
});

describe("omitMessagesAlreadyInChat", () => {
  it("drops a queued message whose id already appears in the completed list", () => {
    // Busy-agent counterpart of the merge dedup above: while the agent is busy
    // the queued list renders in its own bar, so a queued copy of an
    // already-sent id would show as a stuck queued message there.
    const sent = makeMessage("agm_dup");
    const queuedDuplicate = makeMessage("agm_dup");
    const queuedDistinct = makeMessage("agm_other");

    const filtered = omitMessagesAlreadyInChat([queuedDuplicate, queuedDistinct], [sent]);

    expect(filtered.map((message) => message.id)).toEqual(["agm_other"]);
  });

  it("keeps all queued messages when none overlap with the completed list", () => {
    const sent = makeMessage("a");
    const queuedFirst = makeMessage("b");
    const queuedSecond = makeMessage("c");

    const filtered = omitMessagesAlreadyInChat([queuedFirst, queuedSecond], [sent]);

    expect(filtered.map((message) => message.id)).toEqual(["b", "c"]);
  });
});

describe("reference stability and memoization", () => {
  // The chat view remounts on every agent switch and rebuilds its derived data
  // from scratch. These behaviors let that rebuild reuse the prior computation
  // when the underlying message array is unchanged (idle agent, nothing queued).
  it("mergeChatAndQueuedMessages returns the input reference when nothing is queued", () => {
    const messages = [makeMessage("a"), makeMessage("b")];
    // Same reference out — this is what lets the builder caches below hit on remount.
    expect(mergeChatAndQueuedMessages(messages, [])).toBe(messages);
  });

  it("buildToolResultMap caches by input-array reference", () => {
    const messages = [makeMessage("a")];
    const first = buildToolResultMap(messages);
    expect(buildToolResultMap(messages)).toBe(first); // same reference -> cached result
    expect(buildToolResultMap([...messages])).not.toBe(first); // new reference -> recomputed
  });
});
