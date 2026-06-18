import { Box, Flex, Spinner, Text, TextField } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { type ReactElement, useState } from "react";

import { PLUGIN_ID } from "../constants.ts";
import { searchIssues } from "../linear/client.ts";
import { useDebouncedValue } from "../hooks/useDebouncedValue.ts";

/** Search Linear and pin a chosen issue into the panel. */
export const QuickSearch = ({
  apiKey,
  pinnedIds,
  onPin,
}: {
  apiKey: string;
  pinnedIds: ReadonlyArray<string>;
  onPin: (identifier: string) => void;
}): ReactElement => {
  const [term, setTerm] = useState<string>("");
  const debouncedTerm = useDebouncedValue(term.trim(), 250);
  const isActive = debouncedTerm.length >= 2;

  const { data: results, isFetching } = useQuery({
    queryKey: [PLUGIN_ID, "search", debouncedTerm],
    queryFn: ({ signal }) => searchIssues({ apiKey, term: debouncedTerm, signal }),
    enabled: isActive,
    staleTime: 30_000,
  });

  const handlePick = (identifier: string): void => {
    onPin(identifier);
    setTerm("");
  };

  return (
    <Box style={{ position: "relative" }}>
      <TextField.Root
        size="1"
        placeholder="Search Linear issues to pin…"
        value={term}
        onChange={(e) => setTerm(e.target.value)}
      >
        <TextField.Slot>
          <Search size={14} />
        </TextField.Slot>
        {isActive && isFetching && (
          <TextField.Slot>
            <Spinner size="1" />
          </TextField.Slot>
        )}
      </TextField.Root>
      {isActive && results && results.length > 0 && (
        <Box
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            right: 0,
            zIndex: 10,
            maxHeight: 240,
            overflowY: "auto",
            background: "var(--color-panel-solid)",
            border: "1px solid var(--gray-5)",
            borderRadius: "var(--radius-3)",
            boxShadow: "var(--shadow-4)",
          }}
        >
          {results.map((result) => {
            const alreadyPinned = pinnedIds.includes(result.identifier);
            return (
              <Flex
                key={result.identifier}
                align="center"
                gap="2"
                px="2"
                py="1"
                aria-disabled={alreadyPinned}
                onClick={() => !alreadyPinned && handlePick(result.identifier)}
                style={{ cursor: alreadyPinned ? "default" : "pointer", opacity: alreadyPinned ? 0.5 : 1 }}
              >
                <Text size="1" color="gray" style={{ fontFamily: "var(--code-font-family)", flexShrink: 0 }}>
                  {result.identifier}
                </Text>
                <Text size="1" truncate style={{ flexGrow: 1 }}>
                  {result.title}
                </Text>
                {alreadyPinned && (
                  <Text size="1" color="gray">
                    pinned
                  </Text>
                )}
              </Flex>
            );
          })}
        </Box>
      )}
    </Box>
  );
};
