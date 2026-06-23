import { Button, Flex, Link, Spinner, Text } from "@radix-ui/themes";
import { Command } from "cmdk";
import { LockIcon, SearchIcon } from "lucide-react";
import type { KeyboardEvent, ReactElement, Ref, SyntheticEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { RemoteRepo } from "~/api";
import { ElementIds } from "~/api";
import { HTTPException } from "~/common/Errors.ts";
import { formatRelativeTime } from "~/common/formatRelativeTime.ts";

import styles from "./RemoteRepoCombobox.module.scss";
import type { RemoteProvider } from "./SourceRadioCards.tsx";
import { REMOTE_REPOS_INITIAL_LIMIT, useRemoteRepos } from "./useRemoteRepos.ts";

export type { RemoteRepo };

const DEBOUNCE_MS = 200;
const VISIBLE_RESULTS = REMOTE_REPOS_INITIAL_LIMIT;

// Hoisted so the row Links don't allocate fresh handlers on every render.
const stopEventPropagation = (event: SyntheticEvent): void => {
  event.stopPropagation();
};

type RemoteRepoRowProps = {
  repo: RemoteRepo;
  isSelected: boolean;
  onSelect: (repo: RemoteRepo) => void;
};

const RemoteRepoRow = ({ repo, isSelected, onSelect }: RemoteRepoRowProps): ReactElement => (
  <Command.Item
    value={repo.fullName}
    onSelect={() => onSelect(repo)}
    className={`${styles.row} ${isSelected ? styles.rowSelected : ""}`}
    data-testid={ElementIds.ADD_REPO_REPO_COMBOBOX_ITEM}
    data-repo-full-name={repo.fullName}
  >
    <Flex align="center" gap="2" className={styles.rowInfo}>
      <Link
        href={repo.cloneUrl.replace(/\.git$/, "")}
        target="_blank"
        rel="noreferrer"
        size="2"
        weight="medium"
        color="gray"
        highContrast
        underline="hover"
        className={styles.name}
        // Without this, cmdk's Item click handler fires before the Link
        // navigates, selecting the repo instead of opening it.
        onPointerDown={stopEventPropagation}
        onClick={stopEventPropagation}
      >
        {repo.fullName}
      </Link>
      {repo.isPrivate && <LockIcon size={12} className={styles.lockIcon} />}
      {repo.pushedAt && (
        <>
          <Text size="2" color="gray" className={styles.dot} aria-hidden>
            ·
          </Text>
          <Text size="2" color="gray" className={styles.date}>
            {formatRelativeTime(repo.pushedAt)}
          </Text>
        </>
      )}
    </Flex>
    <Button size="1" variant="surface" tabIndex={-1}>
      Select
    </Button>
  </Command.Item>
);

type RemoteRepoComboboxProps = {
  provider: RemoteProvider;
  onSelect: (repo: RemoteRepo) => void;
  onNotConfigured: () => void;
  inputRef?: Ref<HTMLInputElement>;
};

export const RemoteRepoCombobox = ({
  provider,
  onSelect,
  onNotConfigured,
  inputRef,
}: RemoteRepoComboboxProps): ReactElement => {
  const [query, setQuery] = useState<string>("");
  const [debouncedQuery, setDebouncedQuery] = useState<string>("");
  // Controlled cmdk selection. Empty string = nothing highlighted; cmdk would
  // otherwise auto-select the first item on mount / whenever the result list
  // changes, which contradicts the "keyboard-only ring" behavior we want.
  const [selectedValue, setSelectedValue] = useState<string>("");
  // The ring should only appear after the user has actually pressed an arrow
  // key. Without this gate, every refetch lets cmdk's auto-select-first fire
  // onValueChange, lighting up the ring while the user is still typing.
  const hasArrowedRef = useRef<boolean>(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const clearHighlight = useCallback((): void => {
    hasArrowedRef.current = false;
    setSelectedValue("");
  }, []);

  // Clear the highlight whenever the query changes — the previously
  // highlighted repo may not exist in the new result set, and a refetch
  // will re-trigger cmdk's auto-select.
  useEffect(() => {
    clearHighlight();
  }, [debouncedQuery, clearHighlight]);

  const handleSelectionChange = useCallback((next: string): void => {
    if (!hasArrowedRef.current) {
      // cmdk's auto-select-on-mount; ignore until the user explicitly arrows.
      return;
    }
    setSelectedValue(next);
  }, []);

  const { data, isPending, isFetching, isError, error } = useRemoteRepos(provider, debouncedQuery, VISIBLE_RESULTS);

  const visibleRepos = (data ?? []).slice(0, VISIBLE_RESULTS);

  const handleInputKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>): void => {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      if (hasArrowedRef.current) return;
      // First arrow press: cmdk has already auto-selected the first row
      // internally, so its default keydown would advance to the *second*
      // row. Intercept and seed our highlight on the first/last row.
      if (visibleRepos.length === 0) return;
      event.preventDefault();
      hasArrowedRef.current = true;
      const target = event.key === "ArrowDown" ? visibleRepos[0] : visibleRepos[visibleRepos.length - 1];
      setSelectedValue(target.fullName);
    },
    [visibleRepos],
  );

  // 412 means gh isn't installed/authenticated — bubble that up to the
  // parent so it can swap in the NotConfiguredSection.
  useEffect(() => {
    if (isError && error instanceof HTTPException && error.status === 412) {
      onNotConfigured();
    }
  }, [isError, error, onNotConfigured]);

  const handleQueryChange = useCallback((next: string): void => {
    setQuery(next);
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(next);
    }, DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    return (): void => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // First fetch (no data yet): reserve the placeholder area. The input slot
  // shows the spinner; the results area stays empty so we don't double up on
  // loading affordances.
  let comboboxBody: ReactElement;
  if (isPending) {
    comboboxBody = <Flex align="center" justify="center" className={styles.placeholder} />;
  } else if (isError) {
    const message =
      error instanceof HTTPException ? error.detail : error instanceof Error ? error.message : "Failed to load repos";
    comboboxBody = (
      <Flex className={styles.placeholder}>
        <Text size="2" color="red">
          {message}
        </Text>
      </Flex>
    );
  } else if (visibleRepos.length === 0) {
    comboboxBody = (
      <Flex className={styles.placeholder}>
        <Text size="2" color="gray">
          No repos found
        </Text>
      </Flex>
    );
  } else {
    comboboxBody = (
      <>
        {visibleRepos.map((repo) => (
          <RemoteRepoRow
            key={repo.fullName}
            repo={repo}
            isSelected={selectedValue === repo.fullName}
            onSelect={onSelect}
          />
        ))}
      </>
    );
  }

  return (
    <Command
      className={styles.root}
      shouldFilter={false}
      disablePointerSelection
      value={selectedValue}
      onValueChange={handleSelectionChange}
      label="Search repositories"
      // Right-click anywhere in the combobox dismisses the highlight — the
      // user is heading somewhere else (paste, inspect, browser context).
      onContextMenu={clearHighlight}
    >
      <div className={styles.inputWrapper}>
        <SearchIcon size={14} className={styles.searchIcon} />
        <Command.Input
          ref={inputRef}
          className={styles.input}
          value={query}
          onValueChange={handleQueryChange}
          placeholder="Search your repositories…"
          onKeyDown={handleInputKeyDown}
          onBlur={clearHighlight}
          data-testid={ElementIds.ADD_REPO_REPO_COMBOBOX_INPUT}
        />
        {isFetching && (
          <span className={styles.spinnerSlot}>
            <Spinner size="1" />
          </span>
        )}
      </div>
      <Command.List className={styles.results}>{comboboxBody}</Command.List>
    </Command>
  );
};
