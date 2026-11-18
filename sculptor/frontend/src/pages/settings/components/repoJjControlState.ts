import type { JjColocationState, ProjectJjState } from "~/api";

/** What the "colocated jj repository" switch shows. */
export type ColocationSwitchState =
  | { kind: "UNAVAILABLE" }
  | { kind: "INITIALIZING" }
  | { kind: "ON_LOCKED" }
  | { kind: "FAILED"; error: string }
  | { kind: "OFF" };

/**
 * The colocation switch, from the streamed state, whether a colocation request
 * is still settling, and JJ_AVAILABLE.
 *
 * A request settles once the stream reports the colocation it started; until
 * then the switch shows it initializing. While jj is unavailable the backend
 * cannot read colocation and reports ABSENT, so availability comes first.
 */
export const getColocationSwitchState = (inputs: {
  isJjAvailable: boolean;
  jjState: ProjectJjState | null;
  isColocationRequested: boolean;
}): ColocationSwitchState => {
  if (!inputs.isJjAvailable) {
    return { kind: "UNAVAILABLE" };
  }
  const colocation = inputs.jjState?.colocation ?? "ABSENT";
  if (colocation === "COLOCATED") {
    return { kind: "ON_LOCKED" };
  }

  if (colocation === "INITIALIZING" || inputs.isColocationRequested) {
    return { kind: "INITIALIZING" };
  }

  if (colocation === "FAILED") {
    return { kind: "FAILED", error: inputs.jjState?.colocationError ?? "" };
  }
  return { kind: "OFF" };
};

/** What the "use jj for new workspaces" switch shows. */
export type UseJjSwitchState =
  | { kind: "UNAVAILABLE"; isChecked: boolean }
  | { kind: "NOT_COLOCATED"; isChecked: boolean }
  | { kind: "SAVING"; isChecked: boolean }
  | { kind: "ENABLED"; isChecked: boolean };

/**
 * The "use jj for new workspaces" switch, from JJ_AVAILABLE, the streamed
 * colocation, the project's stored flag, and the value of a pending request.
 *
 * While a request is pending it shows the requested value and takes no other
 * request; otherwise it shows the stored value. Nothing is written ahead of
 * the server.
 */
export const getUseJjSwitchState = (inputs: {
  isJjAvailable: boolean;
  colocation: JjColocationState | undefined;
  storedValue: boolean;
  requestedValue: boolean | undefined;
}): UseJjSwitchState => {
  const isChecked = inputs.requestedValue ?? inputs.storedValue;
  if (!inputs.isJjAvailable) {
    return { kind: "UNAVAILABLE", isChecked };
  }

  if (inputs.colocation !== "COLOCATED") {
    return { kind: "NOT_COLOCATED", isChecked };
  }

  if (inputs.requestedValue !== undefined) {
    return { kind: "SAVING", isChecked };
  }
  return { kind: "ENABLED", isChecked };
};
