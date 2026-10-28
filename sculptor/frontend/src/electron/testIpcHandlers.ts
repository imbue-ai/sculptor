// IPC handlers registered only when running under pytest
// (gated on PYTEST_CURRENT_TEST in main.ts). These expose surfaces that
// integration tests need but production builds must not, so they live in
// their own module and are never imported in normal runs.

import { clipboard, type IpcMain, webContents } from "electron";

import { TEST_BROWSER_WEBVIEW_EXECUTE_CHANNEL_NAME, TEST_READ_CLIPBOARD_PNG_CHANNEL_NAME } from "./constants";

export const registerTestIpcHandlers = (ipcMain: IpcMain): void => {
  // Lets integration tests run JavaScript inside a Browser panel webview's
  // guest page via its webContentsId.
  ipcMain.handle(TEST_BROWSER_WEBVIEW_EXECUTE_CHANNEL_NAME, async (_event, webContentsId: number, code: string) => {
    const contents = webContents.fromId(webContentsId);
    if (!contents) {
      throw new Error(`No webContents with id ${webContentsId}`);
    }
    return contents.executeJavaScript(code, true);
  });

  // Reads the system clipboard PNG image so tests can verify the
  // screenshot-to-clipboard feature without relying on renderer-side
  // clipboard APIs (which require focus + permission grants).
  ipcMain.handle(TEST_READ_CLIPBOARD_PNG_CHANNEL_NAME, async () => {
    const items = await clipboard.read();
    const pngItem = items.find((item) => item.types.includes("image/png"));
    if (!pngItem) return null;
    const png = await pngItem.getType("image/png");
    return png.arrayBuffer();
  });
};
