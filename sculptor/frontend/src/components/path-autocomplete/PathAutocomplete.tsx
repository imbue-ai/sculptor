import { Flex, ScrollArea, Spinner } from "@radix-ui/themes";
import { Command } from "cmdk";
import { FolderIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { DirectoryEntry } from "~/api";
import { ElementIds } from "~/api";
import { KeyboardHint } from "~/components/KeyboardHint.tsx";
import { getMetaKey, isModifierPressed } from "~/electron/utils.ts";

import { detectHomeDirPrefix } from "./detectHomeDirPrefix.ts";
import styles from "./PathAutocomplete.module.scss";

const DEBOUNCE_MS = 250;

type PathAutocompleteProps = {
  onSubmit: (path: string) => void;
  placeholder?: string;
  disabled?: boolean;
  fetchDirectories: (path: string) => Promise<Array<DirectoryEntry>>;
  value?: string;
  onValueChange?: (value: string) => void;
  inputTestId?: string;
  autoFocus?: boolean;
};

/**
 * Given a full path from the backend, returns the display path
 * (collapsing home dir back to ~ if needed) split into a dim parent
 * directory prefix and a bold child name.
 */
const getDisplayPath = (
  fullPath: string,
  homeDirPrefix: string | undefined,
): { parentDir: string; childName: string } => {
  let displayPath = fullPath;

  // Collapse expanded home dir back to ~
  if (homeDirPrefix && fullPath.startsWith(homeDirPrefix)) {
    displayPath = "~" + fullPath.slice(homeDirPrefix.length);
  }

  // Split at last "/" — parent dir is dim context, child name is emphasized
  const lastSlash = displayPath.lastIndexOf("/");
  if (lastSlash >= 0) {
    return {
      parentDir: displayPath.slice(0, lastSlash + 1),
      childName: displayPath.slice(lastSlash + 1),
    };
  }
  return { parentDir: "", childName: displayPath };
};

export const PathAutocomplete = ({
  onSubmit,
  placeholder = "/path/to/repository",
  disabled = false,
  fetchDirectories,
  value: controlledValue,
  onValueChange: controlledOnValueChange,
  inputTestId,
  autoFocus = false,
}: PathAutocompleteProps): ReactElement => {
  const [internalValue, setInternalValue] = useState<string>("");
  const inputValue = controlledValue ?? internalValue;
  const setInputValue = useCallback(
    (newValue: string): void => {
      setInternalValue(newValue);
      controlledOnValueChange?.(newValue);
    },
    [controlledOnValueChange],
  );
  const [items, setItems] = useState<Array<DirectoryEntry>>([]);
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [homeDirPrefix, setHomeDirPrefix] = useState<string | undefined>(undefined);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const fetchIdRef = useRef(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const isOpenRef = useRef(isOpen);
  isOpenRef.current = isOpen;

  const closeDropdown = useCallback((): void => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    setIsOpen(false);
    setIsLoading(false);
  }, []);

  const fetchItems = useCallback(
    (path: string): void => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      const requestId = ++fetchIdRef.current;
      debounceRef.current = setTimeout(() => {
        setIsLoading(true);
        fetchDirectories(path)
          .then((results) => {
            // Discard stale responses from earlier requests
            if (requestId !== fetchIdRef.current) return;

            setItems(results);
            setIsOpen(results.length > 0);

            // Detect home directory prefix from first tilde-based query
            if (path.startsWith("~") && results.length > 0 && homeDirPrefix === undefined) {
              const detected = detectHomeDirPrefix(path, results[0].path);
              if (detected !== undefined) {
                setHomeDirPrefix(detected);
              }
            }
          })
          .catch(() => {
            if (requestId !== fetchIdRef.current) return;
            setItems([]);
            setIsOpen(false);
          })
          .finally(() => {
            if (requestId !== fetchIdRef.current) return;
            setIsLoading(false);
          });
      }, DEBOUNCE_MS);
    },
    [fetchDirectories, homeDirPrefix],
  );

  const handleFocus = useCallback((): void => {
    if (items.length > 0) {
      setIsOpen(true);
    } else if (inputValue.length > 0 && inputValue.includes("/")) {
      fetchItems(inputValue);
    }
  }, [items, inputValue, fetchItems]);

  const handleInputChange = useCallback(
    (value: string): void => {
      setInputValue(value);
      if (value.endsWith("/") || value === "~") {
        fetchItems(value);
      } else if (value.length > 0 && value.includes("/")) {
        fetchItems(value);
      } else {
        setItems([]);
        setIsOpen(false);
      }
    },
    [setInputValue, fetchItems],
  );

  const handleSelect = useCallback(
    (selectedPath: string): void => {
      // If user typed with ~, keep ~ in the value instead of the expanded path
      let newValue = selectedPath + "/";
      if (homeDirPrefix && inputValue.startsWith("~") && selectedPath.startsWith(homeDirPrefix)) {
        newValue = "~" + selectedPath.slice(homeDirPrefix.length) + "/";
      }
      setInputValue(newValue);
      fetchItems(newValue);
    },
    [setInputValue, fetchItems, homeDirPrefix, inputValue],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent): void => {
      if (e.key === "Enter") {
        // Strip trailing slashes so consumers get a clean path (e.g. ~/code/repo, not ~/code/repo/)
        const submittedPath = inputValue.trim().replace(/\/+$/, "");
        if (isModifierPressed(e) && submittedPath) {
          // Cmd+Enter (Mac) / Ctrl+Enter (non-Mac) submits regardless of dropdown state.
          // stopPropagation keeps the keystroke from bubbling to page-level Cmd+Enter
          // handlers (e.g. NewWorkspaceForm's "submit from anywhere" listener), which
          // would otherwise also fire and create the workspace (SCU-1450).
          e.preventDefault();
          e.stopPropagation();
          closeDropdown();
          onSubmit(submittedPath);
        } else if (!isOpen && submittedPath) {
          e.preventDefault();
          onSubmit(submittedPath);
          setInputValue("");
        }
      }
    },
    [isOpen, inputValue, onSubmit, setInputValue, closeDropdown],
  );

  // Close dropdown on Escape or Tab
  useEffect(() => {
    const handleDismissKeys = (e: KeyboardEvent): void => {
      if (!isOpenRef.current) return;
      const root = rootRef.current;
      if (!root) return;
      if (!root.contains(document.activeElement)) return;

      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        closeDropdown();
      } else if (e.key === "Tab") {
        closeDropdown();
      }
    };
    document.addEventListener("keydown", handleDismissKeys, true);
    return (): void => {
      document.removeEventListener("keydown", handleDismissKeys, true);
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [closeDropdown]);

  // Close dropdown when focus leaves the component or clicking outside
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const handleFocusOut = (e: FocusEvent): void => {
      const relatedTarget = e.relatedTarget as Node | null;
      if (relatedTarget && root.contains(relatedTarget)) return;
      closeDropdown();
    };

    const handleMouseDown = (e: MouseEvent): void => {
      if (!isOpenRef.current) return;
      if (root.contains(e.target as Node)) return;
      closeDropdown();
    };
    root.addEventListener("focusout", handleFocusOut);
    document.addEventListener("mousedown", handleMouseDown);
    return (): void => {
      root.removeEventListener("focusout", handleFocusOut);
      document.removeEventListener("mousedown", handleMouseDown);
    };
  }, [closeDropdown]);

  const isDropdownVisible = isOpen || isLoading;

  return (
    // Intercept Shift+Arrow in capture phase so cmdk doesn't steal the event.
    // cmdk unconditionally calls preventDefault() on ArrowUp/Down, which blocks
    // browser text-selection when Shift is held.  stopPropagation() (without
    // preventDefault()) lets the browser handle selection normally.
    <div
      onKeyDownCapture={(e): void => {
        if (e.shiftKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
          e.stopPropagation();
        }
      }}
    >
      <Command
        className={styles.root}
        shouldFilter={false}
        label="Path autocomplete"
        ref={rootRef}
        onKeyDown={handleKeyDown}
      >
        <Command.Input
          className={styles.input}
          value={inputValue}
          onValueChange={handleInputChange}
          onFocus={handleFocus}
          placeholder={placeholder}
          disabled={disabled}
          data-testid={inputTestId}
          autoFocus={autoFocus}
        />
        {isDropdownVisible && (
          <Command.List className={styles.list}>
            {isLoading && items.length === 0 && (
              <div className={styles.loading}>
                <Spinner size="2" />
              </div>
            )}
            {!isLoading && items.length === 0 && (
              <Command.Empty className={styles.empty}>No matching directories</Command.Empty>
            )}
            {items.length > 0 && (
              <>
                <ScrollArea type="hover" scrollbars="vertical" style={{ maxHeight: 240 }}>
                  {items.map((entry) => (
                    <PathItem key={entry.path} entry={entry} homeDirPrefix={homeDirPrefix} onSelect={handleSelect} />
                  ))}
                </ScrollArea>
                <Flex className={styles.hint} gapX="3" data-testid={ElementIds.PATH_AUTOCOMPLETE_SUBMIT_HINT}>
                  <KeyboardHint keys="Esc" label="close" />
                  <KeyboardHint keys="↵" label="open" />
                  <KeyboardHint keys={`${getMetaKey()}↵`} label="add" />
                </Flex>
              </>
            )}
          </Command.List>
        )}
      </Command>
    </div>
  );
};

const PathItem = ({
  entry,
  homeDirPrefix,
  onSelect,
}: {
  entry: DirectoryEntry;
  homeDirPrefix: string | undefined;
  onSelect: (path: string) => void;
}): ReactElement => {
  const { parentDir, childName } = useMemo(
    () => getDisplayPath(entry.path, homeDirPrefix),
    [entry.path, homeDirPrefix],
  );

  return (
    <Command.Item
      value={entry.path}
      onSelect={onSelect}
      className={styles.item}
      data-testid={ElementIds.PATH_AUTOCOMPLETE_ITEM}
    >
      <FolderIcon size={14} className={styles.itemIcon} />
      <span className={styles.itemPath}>
        {parentDir && <span className={styles.itemPathDim}>{parentDir}</span>}
        <span className={styles.itemPathMatch}>{childName}</span>
      </span>
    </Command.Item>
  );
};
