// Claude-harness error types. Re-exported from the centralized taxonomy
// (`harness/errors.ts`, Task 5.6); kept at this path for the imports the Claude
// harness modules already use.

export {
  AgentClientError,
  AgentCrashed,
  AgentTransientError,
  ClaudeAPIError,
  ClaudeBinaryNotFoundError,
  serializeError,
  type SerializedException,
} from "~/harness/errors";
