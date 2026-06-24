import { EventBus } from "~/events/bus";

export * from "~/events/bus";
export * from "~/events/types";

// The process-wide bus singleton all producers publish to.
export const eventBus = new EventBus();
