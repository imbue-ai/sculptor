import { z } from "zod";

// SQLite has no native enum type; these are stored as text columns and guarded
// by the Zod schemas at the query boundary. Values mirror the Python
// UpperCaseStrEnums in sculptor/sculptor/database/workspace_enums.py.

export const WORKSPACE_INITIALIZATION_STRATEGIES = ["IN_PLACE", "CLONE", "WORKTREE"] as const;
export type WorkspaceInitializationStrategy = (typeof WORKSPACE_INITIALIZATION_STRATEGIES)[number];
export const workspaceInitializationStrategySchema = z.enum(WORKSPACE_INITIALIZATION_STRATEGIES);

export const DIFF_STATUSES = ["NONE", "GENERATING", "READY"] as const;
export type DiffStatus = (typeof DIFF_STATUSES)[number];
export const diffStatusSchema = z.enum(DIFF_STATUSES);
