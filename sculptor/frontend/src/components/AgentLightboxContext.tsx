import type { ReactElement, ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState } from "react";

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
  taskId?: string;
  children: ReactNode;
};

export const AgentLightboxProvider = ({ taskId, children }: AgentLightboxProviderProps): ReactElement => {
  const listsRef = useRef<Map<string, ListEntry>>(new Map());
  // forceUpdate triggers a re-render so allMedia (computed from the mutable ref) reflects the latest state.
  const [, forceUpdate] = useReducer((n: number) => n + 1, 0);
  const [lightboxPath, setLightboxPath] = useState<string | null>(null);

  // Reset media registry and close lightbox when switching agents. Resetting in
  // an effect rather than remounting the subtree (via key={taskId}) avoids scroll
  // container DOM element swaps and visible scroll flickering.
  useEffect(() => {
    listsRef.current.clear();
    setLightboxPath(null);
    forceUpdate();
  }, [taskId]);

  const registerMedia = useCallback((listId: string, order: number, media: ReadonlyArray<LightboxMediaFile>): void => {
    listsRef.current.set(listId, { order, media });
    forceUpdate();
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

  // Computed fresh each render; forceUpdate() is called whenever listsRef changes.
  const allMedia = [...listsRef.current.values()].sort((a, b) => a.order - b.order).flatMap(({ media }) => [...media]);

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
