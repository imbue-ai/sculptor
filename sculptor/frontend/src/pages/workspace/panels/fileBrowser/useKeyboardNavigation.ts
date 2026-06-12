import { useCallback, useState } from "react";

type KeyboardNavigationItem = {
  path: string;
  type: "file" | "directory";
};

type UseKeyboardNavigationParams = {
  items: Array<KeyboardNavigationItem>;
  expandedFolders: Set<string>;
  onToggleExpand: (path: string) => void;
  onFileOpen: (path: string) => void;
};

type UseKeyboardNavigationResult = {
  focusedIndex: number;
  setFocusedIndex: (index: number) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
};

const findParentIndex = (items: Array<KeyboardNavigationItem>, currentIndex: number): number => {
  const currentPath = items[currentIndex].path;
  const lastSlash = currentPath.lastIndexOf("/");
  if (lastSlash <= 0) {
    return -1;
  }
  const parentPath = currentPath.slice(0, lastSlash);

  for (let i = currentIndex - 1; i >= 0; i--) {
    if (items[i].path === parentPath && items[i].type === "directory") {
      return i;
    }
  }

  return -1;
};

export const useKeyboardNavigation = ({
  items,
  expandedFolders,
  onToggleExpand,
  onFileOpen,
}: UseKeyboardNavigationParams): UseKeyboardNavigationResult => {
  const [focusedIndex, setFocusedIndex] = useState(-1);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent): void => {
      if (items.length === 0) {
        return;
      }

      switch (e.key) {
        case "ArrowDown": {
          e.preventDefault();
          setFocusedIndex((prev) => Math.min(prev + 1, items.length - 1));
          break;
        }

        case "ArrowUp": {
          e.preventDefault();
          setFocusedIndex((prev) => Math.max(prev - 1, 0));
          break;
        }

        case "ArrowRight": {
          e.preventDefault();
          if (focusedIndex < 0 || focusedIndex >= items.length) break;
          const item = items[focusedIndex];
          if (item.type === "directory") {
            if (!expandedFolders.has(item.path)) {
              onToggleExpand(item.path);
            } else {
              // Move to first child
              setFocusedIndex(Math.min(focusedIndex + 1, items.length - 1));
            }
          }
          break;
        }

        case "ArrowLeft": {
          e.preventDefault();
          if (focusedIndex < 0 || focusedIndex >= items.length) break;
          const leftItem = items[focusedIndex];
          if (leftItem.type === "directory" && expandedFolders.has(leftItem.path)) {
            onToggleExpand(leftItem.path);
          } else {
            const parentIdx = findParentIndex(items, focusedIndex);
            if (parentIdx >= 0) {
              setFocusedIndex(parentIdx);
            }
          }
          break;
        }

        case "Enter": {
          e.preventDefault();
          if (focusedIndex < 0 || focusedIndex >= items.length) break;
          const enterItem = items[focusedIndex];
          if (enterItem.type === "file") {
            onFileOpen(enterItem.path);
          } else {
            onToggleExpand(enterItem.path);
          }
          break;
        }

        case " ": {
          e.preventDefault();
          if (focusedIndex < 0 || focusedIndex >= items.length) break;
          const spaceItem = items[focusedIndex];
          if (spaceItem.type === "directory") {
            onToggleExpand(spaceItem.path);
          }
          break;
        }

        default:
          break;
      }
    },
    [items, focusedIndex, expandedFolders, onToggleExpand, onFileOpen],
  );

  return { focusedIndex, setFocusedIndex, onKeyDown };
};
