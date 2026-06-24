import path from "node:path";

import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { parseEnvFileNames } from "~/config/env_file";
import { getSculptorFolder } from "~/config/sculptor_folder";
import { UserConfigSchema, type UserConfig } from "~/config/settings";
import {
  checkIsUserEmailFieldValid,
  createOrganizationId,
  createUserId,
  getCurrentUserConfig,
  getExecutionInstanceId,
  getPrivacySettingsForTelemetry,
  saveUserConfig,
  userConfigToWire,
  wirePartialToInternal,
} from "~/config/user_config";
import { getOrm } from "~/db/orm";
import { getUserSettings, listActiveRepos } from "~/db/repositories";
import { eventBus } from "~/events";
import { getDependencyService } from "~/services/dependencies";

// Config / onboarding endpoints (web/app.py). config.toml (UserConfig) is the
// source of truth; the wire shape is camelCase (RW-API-3). These routes require
// a session token (the global guard already protects /api/); none are on the
// auth exempt list.

const SCULPTOR_VERSION = "0.0.0";

// --- Wire schemas (camelCase; the OpenAPI source for both clients, RW-API-4) --
//
// The internal UserConfig (settings.ts) is snake_case; this mirrors it
// field-for-field in camelCase. A unit test pins the two key sets together so
// they cannot drift.

const DependencyPathsWireSchema = z
  .object({
    git: z.string().nullable().default(null),
    claude: z.string(),
    pi: z.string(),
  })
  .passthrough();

const PiConfigWireSchema = z
  .object({
    apiKeyEnvVarNames: z.array(z.string()),
  })
  .passthrough();

const CIBabysitterConfigWireSchema = z
  .object({
    enabled: z.boolean(),
    retryCap: z.number().int(),
    pipelineFailedPrompt: z.string(),
    mergeConflictPrompt: z.string(),
    agent: z.unknown().optional(),
  })
  .passthrough();

export const UserConfigWireSchema = z
  .object({
    userEmail: z.string(),
    userFullName: z.string().nullable(),
    userId: z.string(),
    organizationId: z.string(),
    instanceId: z.string(),
    isErrorReportingEnabled: z.boolean(),
    isProductAnalyticsEnabled: z.boolean(),
    isSessionRecordingEnabled: z.boolean(),
    isPrivacyPolicyConsented: z.boolean(),
    isTelemetryLevelSet: z.boolean(),
    keybindings: z.record(z.string(), z.string().nullable()),
    defaultLlm: z.string().nullable(),
    updateChannel: z.enum(["STABLE", "ALPHA"]),
    minFreeDiskGb: z.number(),
    panelLayout: z.unknown().nullable(),
    customActions: z.unknown().nullable(),
    prCreationPrompt: z.string(),
    prPollingEnabled: z.boolean(),
    prPollIntervalSeconds: z.number().int(),
    prPollClosedMultiplier: z.number().int(),
    prDefaultTargetBranch: z.string(),
    fileBrowserDefaultSplitRatio: z.number().int(),
    fileBrowserTabCloseBehavior: z.string(),
    fileBrowserLineWrapping: z.string(),
    fileBrowserDiffViewType: z.string(),
    isAlwaysInterruptAndSend: z.boolean(),
    commitPrompt: z.string(),
    ciBabysitter: CIBabysitterConfigWireSchema,
    dependencyPaths: DependencyPathsWireSchema,
    pi: PiConfigWireSchema,
    envVarOverrideEnabled: z.boolean(),
    isSmoothStreamingEnabled: z.boolean(),
    isPanelLayoutPerWorkspace: z.boolean(),
    enableInPlaceWorkspaces: z.boolean(),
    enableCloneWorkspaces: z.boolean(),
    defaultWorkspaceBranchNamingPattern: z.string(),
    workspaceBranchDeletionPolicy: z.enum([
      "never",
      "delete_if_safe",
      "always",
    ]),
    enableReviewAll: z.boolean(),
    enableEntityMentions: z.boolean(),
    enableRichMarkdownRendering: z.boolean(),
    enablePiAgent: z.boolean(),
    enableFrontendPlugins: z.boolean(),
    defaultFastMode: z.boolean(),
    defaultEffortLevel: z.enum(["low", "medium", "high", "xhigh", "max"]),
  })
  .passthrough();

export const TelemetryInfoSchema = z.object({
  userConfig: UserConfigWireSchema,
  sculptorVersion: z.string(),
  sculptorExecutionInstanceId: z.string(),
});

// FastAPI's HTTPException body shape ({"detail": ...}); mirrored for the 400s.
const ErrorResponseSchema = z.object({ detail: z.string() });

const ConfigStatusResponseSchema = z.object({
  hasEmail: z.boolean(),
  hasPrivacyConsent: z.boolean(),
  hasProject: z.boolean(),
  hasDependenciesPassing: z.boolean(),
});

const EmailConfigRequestSchema = z.object({
  userEmail: z.string().email(),
  fullName: z.string().nullable().optional().default(null),
  didOptInToMarketing: z.boolean().optional().default(false),
  isTelemetryEnabled: z.boolean().optional().default(true),
});

const SkipAccountSetupRequestSchema = z.object({
  isTelemetryEnabled: z.boolean().optional().default(true),
});

const SetTelemetryRequestSchema = z.object({
  enabled: z.boolean(),
});

const UpdateUserConfigRequestSchema = z.object({
  userConfig: z.record(z.string(), z.unknown()),
});

const ProjectEnvVarNamesSchema = z.object({
  projectName: z.string(),
  projectPath: z.string(),
  varNames: z.array(z.string()),
});

const EnvVarNamesResponseSchema = z.object({
  globalVarNames: z.array(z.string()),
  globalEnvPath: z.string(),
  projects: z.array(ProjectEnvVarNamesSchema),
});

// The SDK-facing flags POST /api/v1/config/telemetry owns; PUT /api/v1/config
// rejects requests that would change any of them.
const TELEMETRY_FLAGS = [
  "is_error_reporting_enabled",
  "is_product_analytics_enabled",
  "is_session_recording_enabled",
] as const;

// _display_path: collapse the user's home dir to ~ for display.
function displayPath(target: string): string {
  const home = process.env.HOME ?? "";
  if (
    home !== "" &&
    (target === home || target.startsWith(`${home}${path.sep}`))
  ) {
    const relative = path.relative(home, target);
    return relative === "" ? "~" : `~/${relative}`;
  }
  return target;
}

function buildTelemetryInfo(
  config: UserConfig,
): z.infer<typeof TelemetryInfoSchema> {
  return {
    userConfig: userConfigToWire(config) as z.infer<
      typeof UserConfigWireSchema
    >,
    sculptorVersion: SCULPTOR_VERSION,
    sculptorExecutionInstanceId: getExecutionInstanceId(),
  };
}

// Notify ScopeAll stream connections that user settings changed (Task 4.1/4.4).
// A no-op for the wire when no user_settings row exists, but kept faithful to
// the data-model-change contract.
function publishUserSettingsChanged(): void {
  const row = getUserSettings(getOrm());
  if (row !== undefined) {
    eventBus.publish({
      kind: "data_model_change",
      changedEntities: [{ type: "user_settings", id: row.objectId }],
    });
  }
}

export async function registerConfigRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();

  typed.get(
    "/api/v1/config/status",
    { schema: { response: { 200: ConfigStatusResponseSchema } } },
    async () => {
      const config = getCurrentUserConfig();
      const hasProject = listActiveRepos(getOrm()).length > 0;
      // deps_passing = git installed AND claude installed AND claude version
      // not out-of-range (None counts as passing — Python web/app.py L2558-2560).
      const deps = await getDependencyService().getStatus();
      const hasDependenciesPassing =
        deps.git.installed &&
        deps.claude.installed &&
        deps.claude.isVersionInRange !== false;
      return {
        hasEmail:
          config.user_email !== "" && checkIsUserEmailFieldValid(config),
        hasPrivacyConsent: config.is_privacy_policy_consented,
        hasProject,
        hasDependenciesPassing,
      };
    },
  );

  typed.post(
    "/api/v1/config/email",
    {
      schema: {
        body: EmailConfigRequestSchema,
        response: { 200: TelemetryInfoSchema },
      },
    },
    async (request) => {
      const body = request.body;
      const current = getCurrentUserConfig();
      const updated = UserConfigSchema.parse({
        ...current,
        user_email: body.userEmail,
        user_id: createUserId(body.userEmail),
        user_full_name: body.fullName,
        organization_id: createOrganizationId(body.userEmail),
        is_privacy_policy_consented: true,
        is_telemetry_level_set: true,
        ...getPrivacySettingsForTelemetry(body.isTelemetryEnabled),
      });
      saveUserConfig(updated);
      publishUserSettingsChanged();
      return buildTelemetryInfo(updated);
    },
  );

  typed.post(
    "/api/v1/config/skip_account",
    {
      schema: {
        body: SkipAccountSetupRequestSchema,
        response: { 200: TelemetryInfoSchema },
      },
    },
    async (request) => {
      const body = request.body;
      const current = getCurrentUserConfig();
      const updated = UserConfigSchema.parse({
        ...current,
        is_privacy_policy_consented: true,
        is_telemetry_level_set: true,
        ...getPrivacySettingsForTelemetry(body.isTelemetryEnabled),
      });
      saveUserConfig(updated);
      publishUserSettingsChanged();
      return buildTelemetryInfo(updated);
    },
  );

  typed.post(
    "/api/v1/config/complete",
    { schema: { response: { 200: z.null(), 400: ErrorResponseSchema } } },
    async (_request, reply) => {
      let config = getCurrentUserConfig();
      if (config.user_email !== "" && !checkIsUserEmailFieldValid(config)) {
        return reply.code(400).send({ detail: "Invalid email address" });
      }
      if (config.user_email === "" && !config.is_privacy_policy_consented) {
        return reply
          .code(400)
          .send({ detail: "Welcome step has not been completed" });
      }
      // Backfill consent/telemetry for returning users who onboarded before
      // these fields existed.
      const updates: Record<string, unknown> = {};
      if (!config.is_privacy_policy_consented) {
        updates.is_privacy_policy_consented = true;
      }
      if (!config.is_telemetry_level_set) {
        updates.is_telemetry_level_set = true;
        Object.assign(updates, getPrivacySettingsForTelemetry(true));
      }
      if (Object.keys(updates).length > 0) {
        config = UserConfigSchema.parse({ ...config, ...updates });
        saveUserConfig(config);
        publishUserSettingsChanged();
      }
      return reply.code(200).send(null);
    },
  );

  typed.get(
    "/api/v1/config",
    { schema: { response: { 200: UserConfigWireSchema } } },
    async () => {
      return userConfigToWire(getCurrentUserConfig()) as z.infer<
        typeof UserConfigWireSchema
      >;
    },
  );

  typed.put(
    "/api/v1/config",
    {
      schema: {
        body: UpdateUserConfigRequestSchema,
        response: { 200: UserConfigWireSchema, 400: ErrorResponseSchema },
      },
    },
    async (request, reply) => {
      const current = getCurrentUserConfig();
      const patch = request.body.userConfig;
      // Reject attempts to change telemetry consent here (camel or snake key).
      const internalKeyValues = wirePartialToInternal(patch);
      for (const flag of TELEMETRY_FLAGS) {
        if (!(flag in internalKeyValues)) {
          continue;
        }
        if (internalKeyValues[flag] !== current[flag]) {
          return reply.code(400).send({
            detail:
              "Use POST /api/v1/config/telemetry to change telemetry consent.",
          });
        }
      }
      const merged = UserConfigSchema.parse({
        ...current,
        ...internalKeyValues,
      });
      saveUserConfig(merged);
      publishUserSettingsChanged();
      return userConfigToWire(merged) as z.infer<typeof UserConfigWireSchema>;
    },
  );

  typed.post(
    "/api/v1/config/telemetry",
    {
      schema: {
        body: SetTelemetryRequestSchema,
        response: { 200: UserConfigWireSchema },
      },
    },
    async (request) => {
      const current = getCurrentUserConfig();
      const updated = UserConfigSchema.parse({
        ...current,
        ...getPrivacySettingsForTelemetry(request.body.enabled),
      });
      saveUserConfig(updated);
      publishUserSettingsChanged();
      return userConfigToWire(updated) as z.infer<typeof UserConfigWireSchema>;
    },
  );

  typed.get(
    "/api/v1/env-var-names",
    { schema: { response: { 200: EnvVarNamesResponseSchema } } },
    async () => {
      const sculptorFolder = getSculptorFolder();
      const globalEnvPath = path.join(sculptorFolder, ".env");
      const projects: z.infer<typeof ProjectEnvVarNamesSchema>[] = [];
      for (const repo of listActiveRepos(getOrm())) {
        if (!repo.isPathAccessible || repo.userGitRepoUrl === null) {
          continue;
        }
        if (!repo.userGitRepoUrl.startsWith("file://")) {
          continue;
        }
        const projectPath = repo.userGitRepoUrl.replace("file://", "");
        const varNames = parseEnvFileNames(
          path.join(projectPath, ".sculptor", ".env"),
        );
        if (varNames.length > 0) {
          projects.push({
            projectName: repo.name,
            projectPath: displayPath(projectPath),
            varNames,
          });
        }
      }
      return {
        globalVarNames: parseEnvFileNames(globalEnvPath),
        globalEnvPath: displayPath(globalEnvPath),
        projects,
      };
    },
  );
}
