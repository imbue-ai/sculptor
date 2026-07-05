import semver from "semver";

import type { AutoUpdateStatus, UpdateChannel } from "~/shared/types.ts";

const UPDATE_CHANNEL_DISPLAY_NAMES: Record<UpdateChannel, string> = {
  STABLE: "Stable",
  RC: "Latest",
};

export const getUpdateChannelDisplayName = (channel: UpdateChannel): string => {
  return UPDATE_CHANNEL_DISPLAY_NAMES[channel];
};

/**
 * Returns a human-readable status string for the current auto-update state.
 */
export const getUpdateStatusText = (
  status: AutoUpdateStatus | null,
  channel: UpdateChannel | null,
  currentVersion: string | undefined,
): string => {
  if (!status || status.type === "disabled") {
    return "Auto-updates are disabled.";
  }
  const channelLabel = channel ? getUpdateChannelDisplayName(channel) : "unknown";
  switch (status.type) {
    case "checking":
      return "Checking for updates…";
    case "available":
      return `Update available: v${status.version}.`;
    case "downloading":
      return `Downloading update — ${Math.round(status.percent)}%…`;
    case "ready":
      return `v${status.version} is ready to install.`;
    case "error":
      return `Update error: ${status.message}`;
    case "idle":
      if (
        status.latestChannelVersion &&
        currentVersion &&
        semver.valid(status.latestChannelVersion) &&
        semver.valid(currentVersion) &&
        semver.lt(status.latestChannelVersion, currentVersion)
      ) {
        return `You're on v${currentVersion}, ahead of latest ${channelLabel} release (v${status.latestChannelVersion}).`;
      }

      if (status.latestChannelVersion) {
        return `Up to date — latest ${channelLabel} release: v${status.latestChannelVersion}.`;
      }
      return "Up to date.";
  }
};
