import * as SelectPrimitive from "@radix-ui/react-select";
import { Badge, Box, Flex, ScrollArea, Select, Text, Tooltip } from "@radix-ui/themes";
import { ThickCheckIcon } from "@radix-ui/themes/src/components/icons.tsx";
import { SearchIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { ElementIds } from "~/api";

import styles from "./BranchCombobox.module.scss";

export type BadgeInfo = {
  text: string;
  tooltip?: string;
};

export type BranchWithBadges = {
  branch: string;
  badges: Array<string | BadgeInfo>;
};

type BranchOptionProps = {
  branch: string;
  badges: Array<string | BadgeInfo>;
};

const BranchOption = ({ branch, badges }: BranchOptionProps): ReactElement => {
  return (
    <SelectPrimitive.Item
      value={branch}
      asChild={false}
      className="rt-SelectItem"
      data-testid={ElementIds.BRANCH_OPTION}
    >
      <SelectPrimitive.ItemIndicator className="rt-SelectItemIndicator">
        <ThickCheckIcon className="rt-SelectItemIndicatorIcon" />
      </SelectPrimitive.ItemIndicator>
      <Flex width="100%" gapX="2">
        <Box>
          <Text>{branch}</Text>
        </Box>
        {badges.length > 0 && (
          <Box ml="auto">
            {badges.map((badge, idx) => {
              const badgeText = typeof badge === "string" ? badge : badge.text;
              const badgeTooltip = typeof badge === "string" ? undefined : badge.tooltip;
              const badgeElement = (
                <Badge size="1" ml="1" key={idx}>
                  {badgeText}
                </Badge>
              );
              return badgeTooltip ? (
                <Tooltip key={idx} content={badgeTooltip}>
                  {badgeElement}
                </Tooltip>
              ) : (
                badgeElement
              );
            })}
          </Box>
        )}
      </Flex>
    </SelectPrimitive.Item>
  );
};

type BranchComboboxProps = {
  selectedBranch: string;
  onBranchSelected: (branch: string) => void;
  branches: Array<BranchWithBadges>;
  specialBranchFilter?: (branch: BranchWithBadges) => boolean;

  triggerContent: ReactNode;
  triggerVariant?: "soft" | "ghost";

  disabled?: boolean;
  testId?: string;
  contentTestId?: string;
  className?: string;

  isLoadingBranches?: boolean;

  height?: number;
  onOpenChange?: (open: boolean) => void;
};

export const BranchCombobox = ({
  selectedBranch,
  onBranchSelected,
  branches,
  specialBranchFilter,
  triggerContent,
  triggerVariant = "soft",
  disabled = false,
  testId,
  contentTestId,
  className,
  isLoadingBranches = false,
  height = 270,
  onOpenChange,
}: BranchComboboxProps): ReactElement => {
  const [searchQuery, setSearchQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [lockedWidth, setLockedWidth] = useState<number | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  const { specialBranches, otherBranches } = useMemo(() => {
    const specialFilter = specialBranchFilter ?? ((b: BranchWithBadges): boolean => b.badges.length > 0);
    const special = branches.filter(specialFilter);
    const others = branches.filter((b) => !specialFilter(b));
    return { specialBranches: special, otherBranches: others };
  }, [branches, specialBranchFilter]);

  const { specialBranchesFiltered, otherBranchesFiltered } = useMemo(() => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) {
      return { specialBranchesFiltered: specialBranches, otherBranchesFiltered: otherBranches };
    }

    const filterAndSort = (branches: Array<BranchWithBadges>): Array<BranchWithBadges> => {
      return branches
        .filter(({ branch }) => branch.toLowerCase().includes(query))
        .sort((a, b) => {
          const aLower = a.branch.toLowerCase();
          const bLower = b.branch.toLowerCase();
          const doesAStart = aLower.startsWith(query);
          const doesBStart = bLower.startsWith(query);

          // Prioritize branches that start with the query
          if (doesAStart && !doesBStart) return -1;
          if (!doesAStart && doesBStart) return 1;

          // Otherwise maintain original order (alphabetical within each group)
          return aLower.localeCompare(bLower);
        });
    };

    const specialFiltered = filterAndSort(specialBranches);
    const otherFiltered = filterAndSort(otherBranches);

    return { specialBranchesFiltered: specialFiltered, otherBranchesFiltered: otherFiltered };
  }, [specialBranches, otherBranches, searchQuery]);

  const allFilteredBranches = useMemo(() => {
    return [...specialBranchesFiltered, ...otherBranchesFiltered];
  }, [specialBranchesFiltered, otherBranchesFiltered]);

  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      requestAnimationFrame(() => {
        searchInputRef.current?.focus();
      });
    }
  }, [isOpen, allFilteredBranches]);

  useEffect(() => {
    if (isOpen && contentRef.current && lockedWidth === null) {
      requestAnimationFrame(() => {
        if (contentRef.current) {
          setLockedWidth(contentRef.current.offsetWidth);
        }
      });
    }
  }, [isOpen, lockedWidth]);

  return (
    <Select.Root
      size="1"
      value={selectedBranch}
      onValueChange={(newBranch) => {
        onBranchSelected(newBranch);
        setSearchQuery("");
      }}
      disabled={disabled}
      open={isOpen}
      onOpenChange={(open) => {
        setIsOpen(open);
        if (!open) {
          setSearchQuery("");
          setLockedWidth(null);
        }
        onOpenChange?.(open);
      }}
    >
      <Select.Trigger variant={triggerVariant} className={className} data-testid={testId}>
        {triggerContent}
      </Select.Trigger>
      <Select.Content
        className={styles.selectContent}
        position="popper"
        side="bottom"
        align="start"
        sideOffset={5}
        data-testid={contentTestId}
        onCloseAutoFocus={(e) => {
          e.preventDefault();
        }}
        onPointerDownOutside={(e) => {
          const target = e.target as HTMLElement;
          if (!target.closest('[role="combobox"]')) {
            setIsOpen(false);
          }
        }}
      >
        {isOpen && (
          <Flex
            ref={contentRef}
            direction="column"
            overflow="hidden"
            style={{
              maxHeight: `${height}px`,
              width: lockedWidth ? `${lockedWidth}px` : undefined,
              minWidth: lockedWidth ? undefined : "300px",
              position: "relative",
            }}
          >
            <Box px="2" py="1" className={styles.searchContainer}>
              <Box className={styles.searchInputWrapper}>
                <SearchIcon className={styles.searchIcon} />
                <input
                  ref={searchInputRef}
                  type="text"
                  placeholder="Search branches..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    e.stopPropagation();

                    if (e.key === "Enter" && allFilteredBranches.length === 1) {
                      onBranchSelected(allFilteredBranches[0].branch);
                      setSearchQuery("");
                      setIsOpen(false);
                    }
                  }}
                  className={styles.searchInputField}
                />
              </Box>
            </Box>
            {specialBranchesFiltered.length > 0 && (
              <Box flexShrink="0">
                <Select.Group>
                  {specialBranchesFiltered.map(({ branch, badges }) => (
                    <BranchOption key={branch} branch={branch} badges={badges} />
                  ))}
                </Select.Group>
                {otherBranchesFiltered.length > 0 && <Select.Separator />}
              </Box>
            )}
            <ScrollArea type="auto" scrollbars="vertical" style={{ flex: 1, minHeight: 0 }}>
              <Select.Group>
                {otherBranchesFiltered.map(({ branch, badges }) => (
                  <BranchOption key={branch} branch={branch} badges={badges} />
                ))}
                {isLoadingBranches && allFilteredBranches.length === 0 && (
                  <Box p="4" style={{ textAlign: "center" }}>
                    <Text size="2" color="gray">
                      Loading branches...
                    </Text>
                  </Box>
                )}
                {!isLoadingBranches && allFilteredBranches.length === 0 && searchQuery && (
                  <Box p="4" style={{ textAlign: "center" }}>
                    <Text size="2" color="gray">
                      No branches found matching &quot;{searchQuery}&quot;
                    </Text>
                  </Box>
                )}
              </Select.Group>
            </ScrollArea>
          </Flex>
        )}
      </Select.Content>
    </Select.Root>
  );
};
