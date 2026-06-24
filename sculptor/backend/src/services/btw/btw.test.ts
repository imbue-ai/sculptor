import { afterEach, describe, expect, it } from "vitest";

import { eventBus } from "~/events";
import type { BusEvent } from "~/events/types";
import {
  BtwService,
  type BtwContext,
  type BtwRunner,
  type BtwUpdate,
} from "~/services/btw/btw";

const tick = (): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, 5));

function captureBtw(): { events: BtwUpdate[]; stop: () => void } {
  const events: BtwUpdate[] = [];
  const unsubscribe = eventBus.subscribe((event: BusEvent) => {
    if (event.kind === "btw_update") {
      events.push(event.update as BtwUpdate);
    }
  });
  return { events, stop: unsubscribe };
}

const context: BtwContext = {
  sessionId: "sess-1",
  binaryPath: "/fake/claude",
  cwd: "/tmp",
};

describe("BtwService", () => {
  let stop: (() => void) | undefined;

  afterEach(() => {
    stop?.();
    stop = undefined;
  });

  it("streams a running then done update carrying the answer", async () => {
    const capture = captureBtw();
    stop = capture.stop;
    const runner: BtwRunner = async () => "the read-only answer";
    const service = new BtwService({ runner, resolveContext: () => context });

    service.runBtwForAgent("ws_1", "agt_1", "req_1", "what changed?");
    await tick();

    expect(capture.events.map((e) => e.state)).toEqual(["running", "done"]);
    expect(capture.events[1]?.answer).toBe("the read-only answer");
    expect(capture.events[1]?.request_id).toBe("req_1");
  });

  it("reports an error when there is no active session", async () => {
    const capture = captureBtw();
    stop = capture.stop;
    const service = new BtwService({
      runner: async () => "",
      resolveContext: () => null,
    });

    service.runBtwForAgent("ws_1", "agt_1", "req_1", "hi");
    await tick();

    expect(capture.events).toHaveLength(1);
    expect(capture.events[0]?.state).toBe("error");
  });

  it("a second /btw aborts the first for the same agent", async () => {
    const capture = captureBtw();
    stop = capture.stop;
    const runner: BtwRunner = ({ signal }) =>
      new Promise<string>((resolve, reject) => {
        signal.addEventListener("abort", () => {
          const error = new Error("aborted");
          error.name = "AbortError";
          reject(error);
        });
      });
    const service = new BtwService({ runner, resolveContext: () => context });

    service.runBtwForAgent("ws_1", "agt_1", "req_1", "first");
    service.runBtwForAgent("ws_1", "agt_1", "req_2", "second");
    await tick();

    const aborted = capture.events.find((e) => e.state === "aborted");
    expect(aborted?.request_id).toBe("req_1");
    expect(
      capture.events
        .filter((e) => e.state === "running")
        .map((e) => e.request_id),
    ).toEqual(["req_1", "req_2"]);
  });
});
