import { Button, DropdownMenu, Flex, IconButton, Text } from "@radix-ui/themes";
import { FileText } from "lucide-react";
import type { FocusEvent, ReactElement } from "react";
import { useState } from "react";

import type { ExternalApp, NamingConventionFile } from "~/api";
import { ElementIds, NamingConventionTier } from "~/api";
import { getOpenWithItems, getPreferredApp, openPathInExternalApp, savePreferredApp } from "~/common/openInApp/items";
import { getBackendCapabilities } from "~/common/state/atoms/backendCapabilities";
import { Code } from "~/components/Code.tsx";

import styles from "./NamingConventionsRows.module.scss";
import { inlineCodeStyle } from "./settingsStyles.ts";

type NamingConventionFileEditorProps = {
  label: string;
  badge?: string;
  file: NamingConventionFile;
  /** Starter content shown, and offered, while the file does not exist. */
  template: string;
  hint: string;
  onSave: (content: string) => Promise<void>;
  onOpenError: (message: string) => void;
};

// The row header already shows where the repo lives, so a repo file is named relative to
// it; the user-global file keeps its home-relative display path.
const labelPath = (file: NamingConventionFile): string =>
  file.tier === NamingConventionTier.USER ? file.displayPath : file.path.split("/").slice(-2).join("/");

export const NamingConventionFileEditor = ({
  label,
  badge,
  file,
  template,
  hint,
  onSave,
  onOpenError,
}: NamingConventionFileEditorProps): ReactElement => {
  const doesExist = file.content !== null;
  const savedValue = file.content ?? template;

  const handleBlur = (event: FocusEvent<HTMLTextAreaElement>): void => {
    // An untouched template must not create the file, and unchanged content is not re-saved.
    if (event.target.value !== savedValue) {
      void onSave(event.target.value);
    }
  };

  return (
    <div>
      <div className={styles.fileLabelRow}>
        <label className={styles.fileLabel}>
          <FileText size={14} />
          {label}
          <Code size="1" style={inlineCodeStyle}>
            {labelPath(file)}
          </Code>
          {badge && <span className={styles.fileBadge}>{badge}</span>}
        </label>
        <Flex align="center" gap="2">
          {doesExist ? (
            <Button variant="ghost" size="1" onClick={() => void onSave(template)}>
              Reset to template
            </Button>
          ) : (
            <Text className={styles.notCreated}>Not created</Text>
          )}
          <OpenWithMenu path={file.path} isDisabled={!doesExist} onError={onOpenError} />
        </Flex>
      </div>
      {/* Uncontrolled: `key` re-mounts the textarea when the saved value changes
          (after a save, reset, or delete), so we never copy the prop into local state. */}
      <textarea
        key={savedValue}
        className={`${styles.fileInput} ${doesExist ? "" : styles.fileInputTemplate}`}
        defaultValue={savedValue}
        onBlur={handleBlur}
        rows={10}
        spellCheck={false}
        data-testid={ElementIds.SETTINGS_NAMING_CONVENTION_TEXTAREA}
      />
      <Text as="p" size="1" className={styles.fileHint}>
        {hint}{" "}
        {doesExist
          ? "Saves when you click away; clear the text to delete the file. Only the first 4,000 characters reach the agent."
          : "It doesn't exist yet, so it adds nothing for the agent. Edit the template and click away to create it."}
      </Text>
    </div>
  );
};

type OpenWithMenuProps = {
  path: string;
  isDisabled: boolean;
  onError: (message: string) => void;
};

// The same app list and remembered preference as the workspace header's "Open with"
// menu: one click opens the file in the preferred app, the chevron picks another.
const OpenWithMenu = ({ path, isDisabled, onError }: OpenWithMenuProps): ReactElement | null => {
  const [preferredApp, setPreferredApp] = useState<ExternalApp | null>(getPreferredApp);
  const items = getBackendCapabilities().canOpenInOS ? getOpenWithItems() : [];
  if (items.length === 0) {
    return null;
  }
  const preferredItem = items.find((item) => item.app === preferredApp) ?? null;

  const openWith = (app: ExternalApp): void => {
    savePreferredApp(app);
    setPreferredApp(app);
    void openPathInExternalApp(path, app).then((result) => {
      if (!result.success) {
        const appLabel = items.find((item) => item.app === app)?.label ?? app;
        onError(result.errorMessage ?? `Failed to open ${appLabel}. Please try again.`);
      }
    });
  };

  return (
    <Flex align="center" gap="2">
      {preferredItem && (
        <Button variant="soft" size="1" disabled={isDisabled} onClick={() => openWith(preferredItem.app)}>
          <img src={preferredItem.icon} alt="" width={14} height={14} />
          Open in {preferredItem.label}
        </Button>
      )}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger disabled={isDisabled}>
          {preferredItem ? (
            <IconButton variant="soft" size="1" aria-label="Open with another app">
              <DropdownMenu.TriggerIcon />
            </IconButton>
          ) : (
            <Button variant="soft" size="1">
              Open with
              <DropdownMenu.TriggerIcon />
            </Button>
          )}
        </DropdownMenu.Trigger>
        <DropdownMenu.Content size="1">
          {items.map((item) => (
            <DropdownMenu.Item key={item.app} onSelect={() => openWith(item.app)}>
              <Flex align="center" gap="2">
                <img src={item.icon} alt="" width={14} height={14} />
                {item.label}
              </Flex>
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    </Flex>
  );
};
