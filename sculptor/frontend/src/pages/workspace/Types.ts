import type { ArtifactType, TaskListArtifact } from "../../api";

export type ArtifactsMap = {
  [ArtifactType.PLAN]?: TaskListArtifact;
};
