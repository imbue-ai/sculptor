import type { ReactElement, ReactNode } from "react";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { ImageLightbox } from "./ImageLightbox.tsx";

type LightboxMediaFile = {
  url: string;
  name: string;
  isVideo: boolean;
  path: string;
};

type ListEntry = {
  order: number;
  media: ReadonlyArray<LightboxMediaFile>;
};

type AgentLightboxContextValue = {
  registerMedia: (listId: string, order: number, media: ReadonlyArray<LightboxMediaFile>) => void;
  openLightbox: (filePath: string) => void;
};

// eslint-disable-next-line react-refresh/only-export-components -- context and hook must be co-located with the provider
export const AgentLightboxContext = createContext<AgentLightboxContextValue | null>(null);
// eslint-disable-next-line react-refresh/only-export-components -- hook must live alongside context
export const useAgentLightbox = (): AgentLightboxContextValue | null => useContext(AgentLightboxContext);

type AgentLightboxProviderProps = {
  agentId?: string;
  children: ReactNode;
};

export const AgentLightboxProvider = ({ agentId, children }: AgentLightboxProviderProps): ReactElement => {
  // Registered media is real state (keyed by list id), so the render reads state
  // rather than a mutable ref and updates re-render automatically.
  const [lists, setLists] = useState<ReadonlyMap<string, ListEntry>>(() => new Map());
  const [lightboxPath, setLightboxPath] = useState<string | null>(null);

  // Reset the media registry and close the lightbox when switching agents.
  // Adjusting state during render (comparing agentId to its previous value)
  // instead of remounting via key={agentId} avoids scroll container DOM element
  // swaps and visible scroll flickering, and avoids the extra render an effect
  // would introduce.
  const [prevAgentId, setPrevAgentId] = useState(agentId);
  if (agentId !== prevAgentId) {
    setPrevAgentId(agentId);
    setLists(new Map());
    setLightboxPath(null);
  }

  const registerMedia = useCallback((listId: string, order: number, media: ReadonlyArray<LightboxMediaFile>): void => {
    setLists((prev) => {
      const next = new Map(prev);
      next.set(listId, { order, media });
      return next;
    });
  }, []);

  const openLightbox = useCallback((filePath: string): void => {
    setLightboxPath(filePath);
  }, []);

  const handleClose = useCallback((): void => {
    setLightboxPath(null);
  }, []);

  const contextValue = useMemo<AgentLightboxContextValue>(
    () => ({ registerMedia, openLightbox }),
    [registerMedia, openLightbox],
  );

  const allMedia = useMemo(
    () => [...lists.values()].sort((a, b) => a.order - b.order).flatMap(({ media }) => [...media]),
    [lists],
  );

  const lightboxIndex = lightboxPath != null ? allMedia.findIndex((m) => m.path === lightboxPath) : -1;

  return (
    <AgentLightboxContext.Provider value={contextValue}>
      {children}
      {lightboxIndex >= 0 && (
        <ImageLightbox media={allMedia} initialIndex={lightboxIndex} onClose={handleClose} allowCopyImage />
      )}
    </AgentLightboxContext.Provider>
  );
};
