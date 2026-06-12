import { atom } from "jotai";

import type { HealthCheckResponse } from "~/api";

import type { AnyBackendStatus } from "../../../shared/types.ts";

export const backendStatusAtom = atom<AnyBackendStatus>({
  status: "loading",
  payload: {
    message: "Component mounted, waiting for acknowledgement backend is running.",
  },
});

export const healthCheckDataAtom = atom<HealthCheckResponse | null>(null);

export const hasBackendStartedSuccessfullyAtom = atom(false);
