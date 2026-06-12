import type { ArtifactType, TaskListArtifact } from "../../api";

// ===============================
// Artifact Types
// ===============================

export type ArtifactsMap = {
  [ArtifactType.PLAN]?: TaskListArtifact;
};
