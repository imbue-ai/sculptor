import { useMemo } from "react";

import { AgentTaskStatus, type Task } from "~/api";

export type TaskTiers = {
  tierById: Map<string, number>;
  maxTier: number;
  liveTier: number | null;
};

/**
 * Compute a tier index for each task based on its blockedBy edges.
 *
 * Tier 0 means the task has no dependencies; tier N means the task depends
 * on at least one tier-(N-1) task and no higher. liveTier is the tier of
 * the first in-progress task encountered in input order, or null if none.
 *
 * Dangling blockedBy ids (referencing tasks not in the list) are tolerated
 * via a console.warn and treated as tier 0; the dependent task still gets
 * tier 1. Cycles produce tier 0 for every task involved + a console.warn.
 */
export const useTaskTiers = (tasks: Array<Task> | null): TaskTiers => {
  return useMemo(() => {
    if (!tasks || tasks.length === 0) {
      return { tierById: new Map(), maxTier: 0, liveTier: null };
    }

    const taskById = new Map<string, Task>(tasks.map((t) => [t.id, t]));
    const tierById = new Map<string, number>();
    const visiting = new Set<string>();
    const inCycle = new Set<string>();

    const compute = (id: string): number => {
      const cached = tierById.get(id);
      if (cached !== undefined) return cached;
      if (visiting.has(id)) {
        console.warn(`useTaskTiers: cycle detected involving task ${id}`);
        for (const v of visiting) inCycle.add(v);
        inCycle.add(id);
        return 0;
      }
      visiting.add(id);
      const task = taskById.get(id);
      if (!task) {
        visiting.delete(id);
        return 0;
      }
      let tier = 0;
      for (const dep of task.blockedBy ?? []) {
        if (!taskById.has(dep)) {
          console.warn(`useTaskTiers: task ${id} blockedBy unknown ${dep}; treating as tier 0`);
          tier = Math.max(tier, 1);
          continue;
        }
        tier = Math.max(tier, compute(dep) + 1);
      }
      visiting.delete(id);
      if (inCycle.has(id)) {
        tierById.set(id, 0);
        return 0;
      }
      tierById.set(id, tier);
      return tier;
    };

    for (const task of tasks) {
      compute(task.id);
    }

    // Any task tagged as in-cycle after the pass gets tier 0 even if it
    // wasn't directly visited as the outer-compute root.
    for (const id of inCycle) {
      tierById.set(id, 0);
    }

    let maxTier = 0;
    let liveTier: number | null = null;
    for (const task of tasks) {
      const tier = tierById.get(task.id) ?? 0;
      maxTier = Math.max(maxTier, tier);
      if (liveTier === null && task.status === AgentTaskStatus.IN_PROGRESS) {
        liveTier = tier;
      }
    }

    return { tierById, maxTier, liveTier };
  }, [tasks]);
};
