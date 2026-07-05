type BaseBackendStatusPayload = { message: string };

export type BackendStatusPayloads = {
  loading: BaseBackendStatusPayload;
  running: BaseBackendStatusPayload;
  warning: BaseBackendStatusPayload;
  error: BaseBackendStatusPayload & { stack: string };
  exited: BaseBackendStatusPayload & { code: number | null; signal: NodeJS.Signals | null; stderr: string };
  unresponsive: BaseBackendStatusPayload;
  shutting_down: BaseBackendStatusPayload;
};

export type BackendStatus<T extends keyof BackendStatusPayloads = keyof BackendStatusPayloads> = {
  status: T;
  payload: BackendStatusPayloads[T];
};

export type AnyBackendStatus = BackendStatus<keyof BackendStatusPayloads>;

export type UpdateChannel = "STABLE" | "RC";

export type AutoUpdateStatus =
  | { type: "disabled" }
  | { type: "idle"; channel: UpdateChannel; latestChannelVersion?: string }
  | { type: "checking"; channel: UpdateChannel }
  | { type: "available"; channel: UpdateChannel; version: string }
  | { type: "downloading"; channel: UpdateChannel; percent: number }
  | { type: "ready"; channel: UpdateChannel; version: string }
  | { type: "error"; channel: UpdateChannel; message: string };
