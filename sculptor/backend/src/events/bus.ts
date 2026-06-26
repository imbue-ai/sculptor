import type { BusEvent } from "~/events/types";

export type EventHandler = (event: BusEvent) => void;
export type Unsubscribe = () => void;

// One typed in-process event bus replacing the Python per-task Queue fan-out and
// its by_user/by_project/by_workspace/by_task subscription indices. All
// producers publish here; subscribers (one per /stream/ws connection) filter by
// scope at consumption time.
//
// Dispatch is synchronous and ordered — the partial-chunk folding depends on
// messages arriving in emit order. There is no backpressure: a slow subscriber
// blocks the event loop, so the projection must stay cheap (the warm cache).
export class EventBus {
  private readonly handlers = new Set<EventHandler>();

  publish(event: BusEvent): void {
    // Iterate a snapshot so a handler that unsubscribes (or subscribes) during
    // dispatch doesn't disturb this delivery.
    for (const handler of [...this.handlers]) {
      try {
        handler(event);
      } catch (error) {
        // Isolate a throwing subscriber: it must neither abort delivery to the
        // remaining subscribers nor propagate back into the producer.
        // eslint-disable-next-line no-console
        console.error("Event bus subscriber threw during dispatch", error);
      }
    }
  }

  subscribe(handler: EventHandler): Unsubscribe {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }
}
