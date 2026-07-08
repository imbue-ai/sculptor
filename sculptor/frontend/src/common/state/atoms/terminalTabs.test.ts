import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import { reportTerminalConnectionStatusAtom, terminalConnectionStatusByPanelIdAtom } from "./terminalTabs.ts";

describe("terminalConnectionStatusByPanelIdAtom", () => {
  it("reads a terminal's status from its own slice, and clears when the connection recovers", () => {
    const store = createStore();
    const panelId = "terminal:ws-1:0";
    expect(store.get(terminalConnectionStatusByPanelIdAtom(panelId))).toBeUndefined();

    store.set(reportTerminalConnectionStatusAtom, { panelId, status: "reconnecting" });
    expect(store.get(terminalConnectionStatusByPanelIdAtom(panelId))).toBe("reconnecting");

    // A healthy status (or null, on unmount) drops the entry, so the slice reads undefined.
    store.set(reportTerminalConnectionStatusAtom, { panelId, status: "connected" });
    expect(store.get(terminalConnectionStatusByPanelIdAtom(panelId))).toBeUndefined();
  });

  it("isolates each panel's slice: a transition on one terminal does not notify another's", () => {
    const store = createStore();
    const first = "terminal:ws-1:0";
    const second = "terminal:ws-1:1";

    // Subscribe to the second terminal's slice and count its re-emits. This is the
    // invariant the whole decoupling rests on: one terminal's transition must not
    // re-render every other terminal's dot.
    let secondNotifications = 0;
    const unsubscribe = store.sub(terminalConnectionStatusByPanelIdAtom(second), () => {
      secondNotifications += 1;
    });

    // Transitions on the FIRST terminal leave the second's selected value (undefined)
    // unchanged, so selectAtom's value-equality guard suppresses the notification.
    store.set(reportTerminalConnectionStatusAtom, { panelId: first, status: "reconnecting" });
    store.set(reportTerminalConnectionStatusAtom, { panelId: first, status: "disconnected" });
    expect(secondNotifications).toBe(0);
    expect(store.get(terminalConnectionStatusByPanelIdAtom(second))).toBeUndefined();

    // A transition on the SECOND terminal notifies its own slice.
    store.set(reportTerminalConnectionStatusAtom, { panelId: second, status: "reconnecting" });
    expect(secondNotifications).toBe(1);
    expect(store.get(terminalConnectionStatusByPanelIdAtom(second))).toBe("reconnecting");

    unsubscribe();
  });
});
