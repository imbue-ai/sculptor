import type { JjColocationState, ProjectJjState } from "~/api";

/** What the "colocated jj repository" switch shows. */
export type ColocationSwitchState =
  | { kind: "UNAVAILABLE" }
  | { kind: "INITIALIZING" }
  | { kind: "ON_LOCKED" }
  | { kind: "FAILED"; error: string }
  | { kind: "OFF" };

/**
 * While jj is unavailable the backend cannot read colocation and reports every
 * repository ABSENT, so availability decides first.
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
 * Nothing is written ahead of the server: while a request is pending the
 * switch shows the requested value and takes no other request, and otherwise
 * it shows the stored value.
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
