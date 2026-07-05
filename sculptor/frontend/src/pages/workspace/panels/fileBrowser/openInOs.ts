import { workspaceOpenInOs } from "~/api";

export const openInOs = async ({
  workspaceId,
  path,
  action,
}: {
  workspaceId: string;
  path: string;
  action: "open_file" | "open_containing_folder";
}): Promise<void> => {
  try {
    await workspaceOpenInOs({
      path: { workspace_id: workspaceId },
      body: { path, action },
    });
  } catch (error) {
    console.error("Error opening in OS:", error);
  }
};
