export const BACKEND_PORT_CHANNEL_NAME = "BACKEND_PORT";
export const BACKEND_STATUS_CHANGE_CHANNEL_NAME = "BACKEND_STATUS_CHANGE";
export const GET_SESSION_TOKEN_CHANNEL_NAME = "get-session-token";
export const GET_BACKEND_URL_CHANNEL_NAME = "get-backend-url";
export const SELECT_PROJECT_DIRECTORY_CHANNEL_NAME = "SELECT_PROJECT_DIRECTORY";
export const GET_CURRENT_BACKEND_STATUS_CHANNEL_NAME = "GET_CURRENT_BACKEND_STATUS";
export const GET_FILE_DATA_CHANNEL_NAME = "GET_FILE_DATA";
export const AUTO_UPDATE_STATUS_CHANNEL_NAME = "AUTO_UPDATE_STATUS";
export const GET_AUTO_UPDATE_STATUS_CHANNEL_NAME = "GET_AUTO_UPDATE_STATUS";
export const AUTO_UPDATE_INSTALL_CHANNEL_NAME = "auto-updater:install-update";
export const AUTO_UPDATE_CHECK_CHANNEL_NAME = "auto-updater:check-for-update";
export const AUTO_UPDATE_SET_CHANNEL_CHANNEL_NAME = "auto-updater:set-update-channel";
export const GET_CUSTOM_BACKEND_SETTINGS_CHANNEL_NAME = "GET_CUSTOM_BACKEND_SETTINGS";
export const SET_CUSTOM_BACKEND_SETTINGS_CHANNEL_NAME = "SET_CUSTOM_BACKEND_SETTINGS";
export const IS_CUSTOM_COMMAND_MODE_CHANNEL_NAME = "IS_CUSTOM_COMMAND_MODE";
export const GET_APP_VERSION_CHANNEL_NAME = "GET_APP_VERSION";
export const CAPTURE_SCREENSHOT_CHANNEL_NAME = "CAPTURE_SCREENSHOT";
export const BROWSER_PANEL_CAPTURE_TO_CLIPBOARD_CHANNEL_NAME = "BROWSER_PANEL_CAPTURE_TO_CLIPBOARD";
export const BROWSER_PANEL_OPEN_IN_PANEL_CHANNEL_NAME = "BROWSER_PANEL_OPEN_IN_PANEL";
export const TEST_BROWSER_WEBVIEW_EXECUTE_CHANNEL_NAME = "__test_browser_webview_execute";
export const TEST_READ_CLIPBOARD_PNG_CHANNEL_NAME = "__test_read_clipboard_png";
export const GET_DEV_INFO_CHANNEL_NAME = "GET_DEV_INFO";
// Sent from main → renderer when the user invokes a zoom action (View menu /
// accelerators) or when an explicit factor is pushed at startup
// (SCULPTOR_ZOOM_FACTOR). The renderer is the source of truth for the page
// zoom factor: it owns the level, calls webFrame.setZoomFactor, and updates
// the --app-zoom CSS custom property — all in one synchronous task so the
// page and the title-bar gutter repaint together (no jitter).
export const ZOOM_COMMAND_CHANNEL_NAME = "ZOOM_COMMAND";

export type ZoomCommand = { kind: "in" } | { kind: "out" } | { kind: "reset" } | { kind: "setFactor"; factor: number };
