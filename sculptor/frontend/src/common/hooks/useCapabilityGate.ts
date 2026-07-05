import { type ElementIds } from "../../api";

/** Copy shown when an affordance is unavailable because the active agent's
 *  harness lacks the underlying capability. One string, reused at every gated
 *  surface. */
export const CAPABILITY_UNSUPPORTED_COPY = "Not supported by this agent harness";

/** The decision a capability gate yields for one affordance. */
export type CapabilityGateState =
  | { readonly enabled: true }
  | { readonly enabled: false; readonly tooltip: string; readonly elementId: ElementIds };

/**
 * Resolve a narrow capability value (the result of a `useAgentSupports<X>`
 * hook) into a gate decision for one affordance. `?? true` keeps the affordance
 * enabled until the agent's capabilities have loaded; a harness that reports the
 * capability `false` yields the disabled treatment, carrying the standardized
 * copy and a stable `elementId` for tests.
 *
 * Not a React hook (calls none); the `use*` name marks that it is evaluated in
 * render beside the `useAgentSupports<X>` hook it consumes.
 */
export const useCapabilityGate = (capabilityValue: boolean | undefined, elementId: ElementIds): CapabilityGateState =>
  (capabilityValue ?? true) ? { enabled: true } : { enabled: false, tooltip: CAPABILITY_UNSUPPORTED_COPY, elementId };
