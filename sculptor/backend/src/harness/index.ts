// The harness layer's cross-cutting surface: the error taxonomy, the registry
// (config→harness selection), and the hello/test harness. The Claude- and
// Pi-specific APIs are imported from their own sub-barrels (`~/harness/claude`,
// `~/harness/pi`) to avoid name collisions between the two harnesses.

export * from "~/harness/errors";
export * from "~/harness/hello";
export * from "~/harness/registry";
