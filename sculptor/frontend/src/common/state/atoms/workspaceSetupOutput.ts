import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { WorkspaceSetupOutputChunk } from "../../../api";

export type SetupOutputBuffer = {
  runId: string;
  maxSeq: number;
  text: string;
};

export const workspaceSetupOutputAtomFamily = atomFamily<string, PrimitiveAtom<SetupOutputBuffer | null>>(() =>
  atom<SetupOutputBuffer | null>(null),
);

function decodeChunkData(data: string): string {
  if (typeof atob === "function") {
    try {
      const binary = atob(data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
      }
      return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    } catch {
      return data;
    }
  }
  return data;
}

export const appendSetupOutputChunkAtom = atom(
  null,
  (getAtom, setAtom, update: { workspaceId: string; chunk: WorkspaceSetupOutputChunk }) => {
    const target = workspaceSetupOutputAtomFamily(update.workspaceId);
    const prev = getAtom(target);
    const decoded = decodeChunkData(update.chunk.data);
    if (!prev || prev.runId !== update.chunk.runId) {
      setAtom(target, { runId: update.chunk.runId, maxSeq: update.chunk.seq, text: decoded });
      return;
    }

    if (update.chunk.seq <= prev.maxSeq) {
      return;
    }
    setAtom(target, {
      runId: prev.runId,
      maxSeq: update.chunk.seq,
      text: prev.text + decoded,
    });
  },
);
