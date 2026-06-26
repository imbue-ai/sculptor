// Pi-harness error types. Re-exported from the centralized taxonomy
// (`harness/errors.ts`); kept at this path for the imports the Pi
// harness modules already use.

export {
  PiBinaryNotFoundError,
  PiCrashError,
  PiVersionMismatchError,
} from "~/harness/errors";
