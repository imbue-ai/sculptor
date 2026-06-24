import type { BusEvent } from "~/events/types";

export type EventHandler = (event: BusEvent) => void;
export type Unsubscribe = () => void;

// One typed in-process event bus replacing the Python per-task Queue fan-out and
// its by_user/by_project/by_workspace/by_task subscription indices (RW-SIMP-1).
// All producers publish here; subscribers (one per /stream/ws connection) filter
// by scope at consumption time (Task 4.5).
//
// Dispatch is synchronous and ordered — the partial-chunk folding (Task 4.2)
// depends on messages arriving in emit order. There is no backpressure: a slow
// subscriber blocks the event loop, so the projection must stay cheap (the warm
// cache, Task 4.4).
export class EventBus {
  private readonly handlers = new Set<EventHandler>();

  publish(event: BusEvent): void {
    // Iterate a snapshot so a handler that unsubscribes (or subscribes) during
    // dispatch doesn't disturb this delivery.
    for (const handler of [...this.handlers]) {
      handler(event);
    }
  }

  subscribe(handler: EventHandler): Unsubscribe {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }
}
