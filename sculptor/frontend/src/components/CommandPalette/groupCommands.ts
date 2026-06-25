import { groupOrder } from "./groups.ts";
import type { Command, CommandGroupId } from "./types.ts";
import { isPageScoped } from "./types.ts";

export type GroupedCommands = Array<{ id: CommandGroupId; commands: Array<Command> }>;

const maxScore = (cmds: ReadonlyArray<Command>, score: (cmd: Command) => number): number => {
  let best = 0;
  for (const cmd of cmds) {
    const s = score(cmd);
    if (s > best) best = s;
  }
  return best;
};

/**
 * Bucket the command list into groups for rendering. Within each group,
 * commands are sorted: top-level → page-scoped, then primary → non-primary,
 * then by explicit `order`, then alphabetical by title.
 *
 * Group order:
 *   - empty query: static `groupOrder` from `groups.ts`.
 *   - non-empty query (and `scoreOf` provided): groups are sorted by
 *     their best command score, descending. This makes a high-confidence
 *     match (e.g. exact title hit on "Dark") win even when its native
 *     group sits below a group whose only match is a weak subsequence.
 */
export const groupCommands = (
  commands: ReadonlyArray<Command>,
  hasQuery: boolean,
  scoreOf?: (cmd: Command) => number,
): GroupedCommands => {
  const byGroup = new Map<CommandGroupId, Array<Command>>();

  for (const cmd of commands) {
    const bucket = byGroup.get(cmd.group);
    if (bucket) {
      bucket.push(cmd);
    } else {
      byGroup.set(cmd.group, [cmd]);
    }
  }

  // Sort each group: top-level entries first (no `onPage`), then
  // page-scoped. Within each scope, primary commands come before
  // non-primary so headliner page-openers (New Workspace, Open Workspace,
  // Workspace actions) lead their group. Within scope+primary, an
  // explicit numeric `order` (if any) takes precedence over the
  // alphabetical fallback so we can spell out specific orderings (e.g.
  // "Workspace actions" before "Switch agent" even though W > S
  // alphabetically). Final tiebreak is alphabetical by title.
  // cmdk's own score-based sort refines the order once a query is typed;
  // this is the empty-query fallback.
  for (const cmds of byGroup.values()) {
    cmds.sort((a, b) => {
      const aScoped = isPageScoped(a) ? 1 : 0;
      const bScoped = isPageScoped(b) ? 1 : 0;
      if (aScoped !== bScoped) return aScoped - bScoped;
      const aPrim = a.primary ? 0 : 1;
      const bPrim = b.primary ? 0 : 1;
      if (aPrim !== bPrim) return aPrim - bPrim;
      const aOrder = a.order ?? Number.POSITIVE_INFINITY;
      const bOrder = b.order ?? Number.POSITIVE_INFINITY;
      if (aOrder !== bOrder) return aOrder - bOrder;
      return a.title.localeCompare(b.title);
    });
  }

  return Array.from(byGroup.entries())
    .filter(([, cmds]) => cmds.length > 0)
    .sort(([aId, aCmds], [bId, bCmds]) => {
      if (hasQuery && scoreOf) {
        const aMax = maxScore(aCmds, scoreOf);
        const bMax = maxScore(bCmds, scoreOf);
        if (aMax !== bMax) return bMax - aMax;
      }
      return groupOrder(aId) - groupOrder(bId);
    })
    .map(([id, cmds]) => ({ id, commands: cmds }));
};
