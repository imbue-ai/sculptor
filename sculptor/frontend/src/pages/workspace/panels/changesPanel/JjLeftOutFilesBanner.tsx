import { Callout, Code, Flex, Link, Text } from "@radix-ui/themes";
import { TriangleAlert } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import { ElementIds } from "~/api";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";

import styles from "./JjLeftOutFilesBanner.module.scss";

const SETTINGS_SECTION_JJ = "JJ";

type JjLeftOutFilesBannerProps = {
  /** The diff artifact's `file_errors`, which in a jj workspace name the new files jj refused to snapshot. */
  fileErrors: Readonly<Record<string, string>>;
};

/**
 * The new files jj left out of a jj workspace's working copy, each with jj's
 * reason. jj does not snapshot a new file over its size limit, so the file is
 * in no file list, diff, commit or push; the Changes panel lists these apart
 * from the changed files because there is no diff to open.
 */
export const JjLeftOutFilesBanner = ({ fileErrors }: JjLeftOutFilesBannerProps): ReactElement | null => {
  const openSettings = useOpenSettings();
  const leftOutFiles = useMemo(
    () => Object.entries(fileErrors).sort(([leftPath], [rightPath]) => leftPath.localeCompare(rightPath)),
    [fileErrors],
  );

  if (leftOutFiles.length === 0) {
    return null;
  }

  const fileCount = leftOutFiles.length;
  return (
    <Callout.Root color="amber" size="1" data-testid={ElementIds.JJ_LEFT_OUT_FILES_BANNER}>
      <Callout.Icon>
        <TriangleAlert size={14} />
      </Callout.Icon>
      <Flex direction="column" gap="2" minWidth="0">
        <Text size="1" weight="medium">
          jj left {fileCount} new {fileCount === 1 ? "file" : "files"} out
        </Text>
        <Text size="1">
          jj does not record a new file over its size limit, so these are in no diff, commit or push. Raise the limit on
          the Jujutsu settings page, or delete the files.
        </Text>
        <Flex direction="column" gap="1">
          {leftOutFiles.map(([path, reason]) => (
            <Flex key={path} direction="column" data-testid={ElementIds.JJ_LEFT_OUT_FILE}>
              <Code size="1" className={styles.path}>
                {path}
              </Code>
              <Text size="1" color="gray">
                {reason}
              </Text>
            </Flex>
          ))}
        </Flex>
        <Link
          href="#"
          size="1"
          onClick={(event) => {
            event.preventDefault();
            openSettings(SETTINGS_SECTION_JJ);
          }}
        >
          Open Jujutsu settings
        </Link>
      </Flex>
    </Callout.Root>
  );
};
