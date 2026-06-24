/**
 * Layout settle: the virtualizer's measurement lifecycle, kept orthogonal to
 * scroll authority.
 *
 * After a task/agent switch the virtualizer invalidates its measurements and the
 * dynamic `paddingEnd` reconverges over a couple of frames. That convergence —
 * not who owns the scroll — is what determines when geometry (scrollHeight,
 * message offsets) is stable. Modelling it as its own tiny machine keeps
 * "measurements are still moving" from being conflated with "a programmatic
 * scroll is in flight".
 */

export type LayoutPhase =
  | { kind: "stable" }
  // Remeasuring after a switch; `paddingEnd`/heights have not converged yet.
  | { kind: "measuring"; sinceTaskId: string };

export type LayoutEvent = { kind: "invalidated"; taskId: string } | { kind: "converged" };

export const initialLayout: LayoutPhase = { kind: "stable" };

export const nextLayout = (state: LayoutPhase, event: LayoutEvent): LayoutPhase => {
  if (event.kind === "invalidated") {
    return { kind: "measuring", sinceTaskId: event.taskId };
  }
  // "converged" — only meaningful while measuring; a no-op when already stable.
  return state.kind === "stable" ? state : { kind: "stable" };
};
