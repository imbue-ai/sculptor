import { Box, Flex, Link, Text } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";

import type { NamingConventionFile, NamingConventionsResponse, NamingConventionTier } from "~/api";
import { ElementIds, getNamingConventions, updateNamingConventions } from "~/api";
import { getErrorMessage } from "~/common/Errors.ts";
import { Code } from "~/components/Code.tsx";
import type { ToastContent } from "~/components/Toast.tsx";
import { ToastType } from "~/components/Toast.tsx";

import { NamingConventionFileEditor } from "./NamingConventionFileEditor.tsx";
import styles from "./NamingConventionsRows.module.scss";
import { SectionTitle } from "./SettingsSection.tsx";
import { inlineCodeStyle } from "./settingsStyles.ts";

type NamingConventionsRowsProps = {
  setToast: (toast: ToastContent | null) => void;
};

const GLOBAL_ROW_KEY = "global";

const withUpdatedFile = (data: NamingConventionsResponse, updated: NamingConventionFile): NamingConventionsResponse => {
  const replace = (file: NamingConventionFile): NamingConventionFile => (file.path === updated.path ? updated : file);
  return {
    ...data,
    globalFile: replace(data.globalFile),
    projects: data.projects.map((project) => ({
      ...project,
      shared: replace(project.shared),
      local: replace(project.local),
    })),
  };
};

const describeFile = (file: NamingConventionFile): string => {
  if (file.content === null) {
    return "not set";
  }
  const lineCount = file.content.trimEnd().split("\n").length;
  return `${lineCount} line${lineCount === 1 ? "" : "s"}`;
};

/**
 * The naming-convention files, one collapsible row for the user-global file and one
 * per repo (shared + local), each expanding into in-place editors.
 */
export const NamingConventionsRows = ({ setToast }: NamingConventionsRowsProps): ReactElement | null => {
  const [data, setData] = useState<NamingConventionsResponse | null>(null);
  const [expandedRowKey, setExpandedRowKey] = useState<string | null>(null);

  useEffect(() => {
    let isIgnored = false;
    void (async (): Promise<void> => {
      try {
        const response = await getNamingConventions({ meta: { skipWsAck: true } });
        if (!isIgnored) {
          setData(response.data);
        }
      } catch (error) {
        if (!isIgnored) {
          setToast({
            title: "Could not load naming conventions",
            description: getErrorMessage(error, "Unknown error"),
            type: ToastType.ERROR,
          });
        }
      }
    })();

    return (): void => {
      isIgnored = true;
    };
  }, [setToast]);

  const saveFile = useCallback(
    async (tier: NamingConventionTier, projectId: string | null, content: string): Promise<void> => {
      try {
        const response = await updateNamingConventions({
          body: { tier, projectId, content },
          meta: { skipWsAck: true },
        });
        setData((previous) => (previous === null ? previous : withUpdatedFile(previous, response.data)));
      } catch (error) {
        setToast({
          title: "Could not save naming conventions",
          description: getErrorMessage(error, "Unknown error"),
          type: ToastType.ERROR,
        });
      }
    },
    [setToast],
  );

  const reportOpenError = useCallback(
    (message: string): void => {
      setToast({ title: "Could not open the file", description: message, type: ToastType.ERROR });
    },
    [setToast],
  );

  if (data === null) {
    return null;
  }

  const toggleRow = (key: string): void => {
    setExpandedRowKey((current) => (current === key ? null : key));
  };

  return (
    <Box className={styles.container} data-testid={ElementIds.SETTINGS_NAMING_CONVENTIONS_LIST}>
      <SectionTitle>Naming conventions</SectionTitle>
      <Text as="p" size="2" className={styles.intro}>
        Markdown files that steer the names above. A repo&apos;s local file overrides its shared one, which overrides
        your global one.
      </Text>
      <ConventionRow
        name="Your conventions (all repos)"
        details={
          <>
            <Code size="2" style={inlineCodeStyle}>
              {data.globalFile.displayPath}
            </Code>{" "}
            — {describeFile(data.globalFile)}
          </>
        }
        isExpanded={expandedRowKey === GLOBAL_ROW_KEY}
        onToggle={() => toggleRow(GLOBAL_ROW_KEY)}
      >
        <NamingConventionFileEditor
          label="Global conventions"
          file={data.globalFile}
          template={data.template}
          hint="Applied in every repo, before each repo's own files."
          onSave={(content) => saveFile(data.globalFile.tier, null, content)}
          onOpenError={reportOpenError}
        />
      </ConventionRow>
      {data.projects.map((project) => (
        <ConventionRow
          key={project.projectId}
          name={project.projectName}
          details={
            <>
              <Code size="2" style={inlineCodeStyle}>
                {project.projectPath}
              </Code>{" "}
              — shared file {describeFile(project.shared)} · local file {describeFile(project.local)}
            </>
          }
          isExpanded={expandedRowKey === project.projectId}
          onToggle={() => toggleRow(project.projectId)}
        >
          <NamingConventionFileEditor
            label="Shared conventions"
            badge="committed"
            file={project.shared}
            template={data.template}
            hint="Committed with the repo, so everyone working in it gets these."
            onSave={(content) => saveFile(project.shared.tier, project.projectId, content)}
            onOpenError={reportOpenError}
          />
          <NamingConventionFileEditor
            label="Local overrides"
            badge="git-ignored"
            file={project.local}
            template={data.template}
            hint="Git-ignored, so just you in this repo; overrides the shared file."
            onSave={(content) => saveFile(project.local.tier, project.projectId, content)}
            onOpenError={reportOpenError}
          />
        </ConventionRow>
      ))}
    </Box>
  );
};

type ConventionRowProps = {
  name: string;
  details: ReactNode;
  isExpanded: boolean;
  onToggle: () => void;
  children: ReactNode;
};

const ConventionRow = ({ name, details, isExpanded, onToggle, children }: ConventionRowProps): ReactElement => (
  <Box className={styles.row} data-testid={ElementIds.SETTINGS_NAMING_CONVENTION_ROW}>
    <Flex align="center" justify="between" gap="3">
      <Flex direction="column" className={styles.rowInfo}>
        <Text weight="medium">{name}</Text>
        <Text size="2" className={styles.rowDetails}>
          {details}
        </Text>
      </Flex>
      <Link
        href="#"
        size="2"
        onClick={(event) => {
          event.preventDefault();
          onToggle();
        }}
        aria-expanded={isExpanded}
        data-testid={ElementIds.SETTINGS_NAMING_CONVENTION_ROW_TOGGLE}
      >
        {isExpanded ? "Collapse" : "Configure"}
      </Link>
    </Flex>
    {isExpanded && (
      <Flex direction="column" gap="4" className={styles.rowConfig}>
        {children}
      </Flex>
    )}
  </Box>
);
