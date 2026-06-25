import { createHash } from "node:crypto";
import {
  chmodSync,
  createWriteStream,
  existsSync,
  mkdirSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync,
} from "node:fs";
import { arch, platform } from "node:os";
import path from "node:path";
import { Writable } from "node:stream";

import { getInternalFolder } from "~/config/sculptor_folder";
import { getCurrentUserConfig } from "~/config/user_config";
import {
  runProcessToCompletion,
  spawnBackgroundProcess,
  type BackgroundProcess,
} from "~/environment/process";
import { eventBus } from "~/events";

// Dependency-management service: the TS port of
// sculptor/sculptor/services/dependency_management_service.py + managed_tools.py.
// It detects the required external binaries (Claude, git, pi), reports their
// version against a supported window, runs managed installs, and drives Claude's
// device-code auth. Status is camelCase wire-shaped directly (it is both the REST
// response and the /stream/ws dependencies_status payload).

export type Dependency = "CLAUDE" | "GIT" | "PI";
type BinaryMode = "MANAGED" | "CUSTOM";

interface BlockedVersionRange {
  minVersion: string;
  maxVersion: string;
}
interface VersionRange {
  minVersion: string;
  maxVersion: string;
  recommendedVersion: string;
  blockedVersions: BlockedVersionRange[];
}

const CLAUDE_VERSION_RANGE: VersionRange = {
  minVersion: "2.1.170",
  maxVersion: "2.99.99",
  recommendedVersion: "2.1.170",
  blockedVersions: [{ minVersion: "2.1.101", maxVersion: "2.1.101" }],
};

const PI_VERSION = "0.78.0";
const PI_VERSION_RANGE: VersionRange = {
  minVersion: PI_VERSION,
  maxVersion: PI_VERSION,
  recommendedVersion: PI_VERSION,
  blockedVersions: [],
};

const DEPENDENCIES_DIR_NAME = "dependencies";
const VERSION_DIR_PREFIX = "version-";
const DOWNLOAD_CHUNK_TIMEOUT_MS = 300_000;
const MANIFEST_FETCH_TIMEOUT_MS = 30_000;

const GCP_BUCKET_BASE_URL =
  "https://storage.googleapis.com/claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases";
const PI_RELEASE_BASE_URL =
  "https://github.com/earendil-works/pi/releases/download";

interface PlatformPin {
  asset: string;
  sha256: string;
}
const PI_PIN: { version: string; platforms: Record<string, PlatformPin> } = {
  version: PI_VERSION,
  platforms: {
    "darwin-arm64": {
      asset: "pi-darwin-arm64.tar.gz",
      sha256:
        "68ebbe4f56a136a1c7bace3393eca4ad0aa1fd9f253b797fd370058bd39fe070",
    },
    "darwin-x64": {
      asset: "pi-darwin-x64.tar.gz",
      sha256:
        "66074b271260068199f47738a172397f1e0b5a3334697dd2acea35bbd3470b1c",
    },
    "linux-x64": {
      asset: "pi-linux-x64.tar.gz",
      sha256:
        "8ac03343d1e1228106e8172157f32d6b882829e46b34feaf577f171a5f1387cc",
    },
  },
};

// (node os.platform(), os.arch()) -> release platform key. Claude omits darwin-x64.
const CLAUDE_PLATFORM_MAP: Record<string, string> = {
  "darwin-arm64": "darwin-arm64",
  "linux-x64": "linux-x64",
};
const PI_PLATFORM_MAP: Record<string, string> = {
  "darwin-arm64": "darwin-arm64",
  "darwin-x64": "darwin-x64",
  "linux-x64": "linux-x64",
};

function currentPlatformLabel(): string {
  // node arch() reports x64/arm64; the maps key on those directly.
  return `${platform()}-${arch()}`;
}

interface ManagedToolDef {
  tool: Dependency;
  versionRange: VersionRange;
  retentionKeep: number;
  binarySubpath: string;
  platformMap: Record<string, string>;
}

const MANAGED_TOOLS: Record<string, ManagedToolDef> = {
  CLAUDE: {
    tool: "CLAUDE",
    versionRange: CLAUDE_VERSION_RANGE,
    retentionKeep: 2,
    binarySubpath: "claude",
    platformMap: CLAUDE_PLATFORM_MAP,
  },
  PI: {
    tool: "PI",
    versionRange: PI_VERSION_RANGE,
    retentionKeep: 1,
    binarySubpath: "pi/pi",
    platformMap: PI_PLATFORM_MAP,
  },
};

function getManagedTool(tool: Dependency): ManagedToolDef | undefined {
  return MANAGED_TOOLS[tool];
}

// --- version parsing + range checks ----------------------------------------

const SEMVER_RE = /(\d+\.\d+\.\d+\S*)/;

function parseSemver(output: string): string | null {
  return SEMVER_RE.exec(output)?.[1] ?? null;
}

function parseGitVersion(output: string): string | null {
  return /git version (\S+)/.exec(output)?.[1] ?? null;
}

function parseVersionForTool(tool: Dependency, output: string): string | null {
  return tool === "GIT" ? parseGitVersion(output) : parseSemver(output);
}

// Compare two MAJOR.MINOR.PATCH versions, ignoring any pre-release suffix
// (sufficient for the pinned ranges these checks gate). Returns -1 / 0 / 1.
function compareVersions(a: string, b: string): number {
  const parse = (v: string): number[] => {
    const core = /^\d+(\.\d+)*/.exec(v)?.[0] ?? "";
    return core.split(".").map((n) => Number.parseInt(n, 10));
  };
  const pa = parse(a);
  const pb = parse(b);
  for (let i = 0; i < 3; i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (diff !== 0) {
      return diff < 0 ? -1 : 1;
    }
  }
  return 0;
}

function isValidVersion(version: string): boolean {
  return /^\d+\.\d+\.\d+/.test(version);
}

function versionRangeForTool(tool: Dependency): VersionRange | null {
  return getManagedTool(tool)?.versionRange ?? null;
}

export function isVersionInRange(
  version: string,
  tool: Dependency = "CLAUDE",
): boolean {
  const range = versionRangeForTool(tool);
  if (range === null) {
    return true;
  }
  if (!isValidVersion(version)) {
    return false;
  }
  if (
    compareVersions(version, range.minVersion) < 0 ||
    compareVersions(version, range.maxVersion) > 0
  ) {
    return false;
  }
  for (const blocked of range.blockedVersions) {
    if (
      compareVersions(version, blocked.minVersion) >= 0 &&
      compareVersions(version, blocked.maxVersion) <= 0
    ) {
      return false;
    }
  }
  return true;
}

// --- binary resolution ------------------------------------------------------

function parseDependencyConfig(value: string): {
  mode: BinaryMode;
  customPath: string | null;
} {
  if (value === "MANAGED") {
    return { mode: "MANAGED", customPath: null };
  }
  if (value === "CUSTOM") {
    return { mode: "CUSTOM", customPath: null };
  }
  return { mode: "CUSTOM", customPath: value };
}

function isValidCustomBinary(value: string): boolean {
  if (value === "") {
    return false;
  }
  if (value.startsWith("/")) {
    return true;
  }
  return !value.includes(" ") && !value.includes("/");
}

function isExecutableFile(file: string): boolean {
  try {
    const stat = statSync(file);
    return stat.isFile() && (stat.mode & 0o111) !== 0;
  } catch {
    return false;
  }
}

// shutil.which equivalent: absolute/relative paths checked directly; bare names
// resolved against PATH.
function which(command: string): string | null {
  if (command.includes("/")) {
    return isExecutableFile(command) ? command : null;
  }
  const pathEnv = process.env.PATH ?? "";
  for (const dir of pathEnv.split(path.delimiter)) {
    if (dir === "") {
      continue;
    }
    const candidate = path.join(dir, command);
    if (isExecutableFile(candidate)) {
      return candidate;
    }
  }
  return null;
}

function getToolDir(tool: Dependency): string {
  return path.join(
    getInternalFolder(),
    DEPENDENCIES_DIR_NAME,
    tool.toLowerCase(),
  );
}

function managedBinarySubpath(tool: Dependency): string {
  return getManagedTool(tool)?.binarySubpath ?? tool.toLowerCase();
}

function isVersionDir(name: string): boolean {
  return (
    name.startsWith(VERSION_DIR_PREFIX) &&
    isValidVersion(name.slice(VERSION_DIR_PREFIX.length))
  );
}

function findManagedBinary(tool: Dependency): string | null {
  const toolDir = getToolDir(tool);
  if (!existsSync(toolDir)) {
    return null;
  }
  const subpath = managedBinarySubpath(tool);
  const range = versionRangeForTool(tool);
  if (range !== null) {
    const recommended = path.join(
      toolDir,
      `${VERSION_DIR_PREFIX}${range.recommendedVersion}`,
      subpath,
    );
    if (existsSync(recommended) && statSync(recommended).isFile()) {
      return recommended;
    }
  }
  const versions: { version: string; binary: string }[] = [];
  for (const entry of readdirSync(toolDir)) {
    if (!isVersionDir(entry)) {
      continue;
    }
    const binary = path.join(toolDir, entry, subpath);
    if (existsSync(binary) && statSync(binary).isFile()) {
      versions.push({
        version: entry.slice(VERSION_DIR_PREFIX.length),
        binary,
      });
    }
  }
  if (versions.length === 0) {
    return null;
  }
  versions.sort((a, b) => compareVersions(b.version, a.version));
  return versions[0]?.binary ?? null;
}

function getManagedVersion(tool: Dependency): string | null {
  const toolDir = getToolDir(tool);
  if (!existsSync(toolDir)) {
    return null;
  }
  const versions = readdirSync(toolDir)
    .filter(isVersionDir)
    .map((name) => name.slice(VERSION_DIR_PREFIX.length));
  if (versions.length === 0) {
    return null;
  }
  versions.sort((a, b) => compareVersions(b, a));
  return versions[0] ?? null;
}

export function resolveBinaryPath(tool: Dependency): string | null {
  const config = getCurrentUserConfig();
  const paths = config.dependency_paths;
  if (tool === "GIT") {
    return paths.git !== null && paths.git !== "" ? paths.git : which("git");
  }
  const raw = tool === "CLAUDE" ? paths.claude : paths.pi;
  const { mode, customPath } = parseDependencyConfig(raw);
  if (mode === "MANAGED") {
    return findManagedBinary(tool);
  }
  const value =
    customPath !== null && customPath !== ""
      ? customPath
      : tool === "CLAUDE"
        ? "claude"
        : "";
  if (value === "" || !isValidCustomBinary(value)) {
    return null;
  }
  return which(value);
}

// --- subprocess probes ------------------------------------------------------

// Run a short-lived command with a timeout, capturing output. Resolves with the
// result; rejects (like Python's ProcessError) on spawn failure or timeout.
function runWithTimeout(
  command: readonly string[],
  timeoutMs: number,
): Promise<{ exitCode: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    let bg: BackgroundProcess;
    try {
      bg = spawnBackgroundProcess(command);
    } catch (error) {
      reject(error instanceof Error ? error : new Error(String(error)));
      return;
    }
    let stdout = "";
    let stderr = "";
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        bg.child.kill("SIGKILL");
        reject(new Error("process timed out"));
      }
    }, timeoutMs);
    bg.child.stdout?.on(
      "data",
      (chunk: Buffer) => (stdout += chunk.toString("utf8")),
    );
    bg.child.stderr?.on(
      "data",
      (chunk: Buffer) => (stderr += chunk.toString("utf8")),
    );
    bg.child.on("error", (error) => {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        reject(error);
      }
    });
    bg.child.on("close", (code) => {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        resolve({ exitCode: code, stdout, stderr });
      }
    });
  });
}

interface DependencyCheckResult {
  installed: boolean;
  path: string | null;
  version: string | null;
}

// --- wire shapes ------------------------------------------------------------

interface VersionRangeInfoWire {
  minVersion: string;
  maxVersion: string;
  recommendedVersion: string;
}
interface InstallProgressWire {
  tool: string;
  bytesDownloaded: number;
  totalBytes: number | null;
}
export interface DependencyInfoWire {
  installed: boolean;
  path: string | null;
  version: string | null;
  isOverride: boolean;
  mode: BinaryMode | null;
  versionRange: VersionRangeInfoWire | null;
  isVersionInRange: boolean | null;
  managedVersion: string | null;
  isAuthenticated: boolean | null;
  installProgress: InstallProgressWire | null;
  installError: string | null;
}
export interface DependenciesStatusWire {
  git: DependencyInfoWire;
  claude: DependencyInfoWire;
  pi: DependencyInfoWire;
}
export interface InstallResultWire {
  success: boolean;
  inProgress: boolean;
  version: string | null;
  path: string | null;
  error: string | null;
}
export interface AuthStartResultWire {
  authUrl: string | null;
  needsCode: boolean;
  success: boolean;
  error: string | null;
}
export interface AuthResultWire {
  success: boolean;
  authUrl: string | null;
  error: string | null;
}

function emptyDependencyInfo(): DependencyInfoWire {
  return {
    installed: false,
    path: null,
    version: null,
    isOverride: false,
    mode: null,
    versionRange: null,
    isVersionInRange: null,
    managedVersion: null,
    isAuthenticated: null,
    installProgress: null,
    installError: null,
  };
}

function rangeInfo(range: VersionRange): VersionRangeInfoWire {
  return {
    minVersion: range.minVersion,
    maxVersion: range.maxVersion,
    recommendedVersion: range.recommendedVersion,
  };
}

interface ResolvedDistribution {
  version: string;
  url: string;
  checksumSha256: string;
  size: number | null;
  archive: "single_binary" | "tarball";
  binarySubpath: string;
}

// Probe (`<binary> --version` / `auth status`) timeout. Read at call time so a
// test under heavy parallel subprocess load can raise it via the env override
// (default mirrors Python's 5s/10s). `base` is the Python-parity default.
function probeTimeoutMs(base: number): number {
  const override = process.env.SCULPTOR_DEP_PROBE_TIMEOUT_MS;
  return override !== undefined && override !== "" ? Number(override) : base;
}

// How long a probed dependency status is served from cache before re-probing.
// Short enough that an external change (a binary installed outside the app) is
// reflected promptly, long enough that polling doesn't re-spawn probes per call.
const DEPENDENCY_STATUS_TTL_MS = 3000;

export class DependencyService {
  private readonly installing = new Set<Dependency>();
  private readonly installProgress = new Map<Dependency, InstallProgressWire>();
  private readonly installError = new Map<Dependency, string>();
  private authSession: {
    process: BackgroundProcess;
    stdout: string;
    stderr: string;
  } | null = null;
  private stopRequested = false;
  private cachedStatus:
    | { status: DependenciesStatusWire; at: number }
    | undefined;
  private statusInFlight: Promise<DependenciesStatusWire> | undefined;

  private async checkInstalled(
    tool: Dependency,
  ): Promise<DependencyCheckResult> {
    const binary = resolveBinaryPath(tool);
    if (binary === null) {
      return { installed: false, path: null, version: null };
    }
    try {
      const result = await runWithTimeout(
        [binary, "--version"],
        probeTimeoutMs(5_000),
      );
      if (result.exitCode !== 0) {
        return { installed: false, path: binary, version: null };
      }
      // Real pi emits --version to stderr; feed both channels for it.
      const text =
        tool === "PI" ? `${result.stdout}\n${result.stderr}` : result.stdout;
      return {
        installed: true,
        path: binary,
        version: parseVersionForTool(tool, text),
      };
    } catch {
      return { installed: false, path: binary, version: null };
    }
  }

  private async checkAuthenticated(tool: Dependency): Promise<boolean | null> {
    if (tool !== "CLAUDE") {
      return null;
    }
    const binary = resolveBinaryPath(tool);
    if (binary === null) {
      return null;
    }
    try {
      const result = await runWithTimeout(
        [binary, "auth", "status"],
        probeTimeoutMs(10_000),
      );
      return result.exitCode === 0;
    } catch {
      return false;
    }
  }

  private buildInfo(
    tool: Dependency,
    check: DependencyCheckResult,
    extra: Partial<DependencyInfoWire>,
  ): DependencyInfoWire {
    return {
      ...emptyDependencyInfo(),
      installed: check.installed,
      path: check.path,
      version: check.version,
      installProgress: this.installProgress.get(tool) ?? null,
      installError: this.installError.get(tool) ?? null,
      ...extra,
    };
  }

  // config/status and dependencies_status are polled, but each computeStatus()
  // spawns version + auth subprocess probes (seconds). Without a cache the polls
  // pile up slow requests that exhaust the browser's small per-host connection
  // pool and stall unrelated requests. Serve a short-lived cache and coalesce
  // concurrent callers onto a single in-flight probe; install/auth flows
  // invalidate it so a freshly installed/authenticated binary shows immediately.
  // The last computed status, or null if never probed. Sync, for the initial
  // WS snapshot (which can't await); a connect also kicks getStatus() to refresh.
  getCachedStatus(): DependenciesStatusWire | null {
    return this.cachedStatus?.status ?? null;
  }

  async getStatus(): Promise<DependenciesStatusWire> {
    const now = Date.now();
    if (
      this.cachedStatus !== undefined &&
      now - this.cachedStatus.at < DEPENDENCY_STATUS_TTL_MS
    ) {
      return this.cachedStatus.status;
    }
    if (this.statusInFlight !== undefined) {
      return this.statusInFlight;
    }
    this.statusInFlight = this.computeStatus()
      .then((status) => {
        this.cachedStatus = { status, at: Date.now() };
        this.statusInFlight = undefined;
        return status;
      })
      .catch((error: unknown) => {
        this.statusInFlight = undefined;
        throw error;
      });
    return this.statusInFlight;
  }

  // Drop the cached status so the next getStatus() re-probes — call after an
  // install or auth change mutates a binary's state.
  invalidateStatusCache(): void {
    this.cachedStatus = undefined;
  }

  private async computeStatus(): Promise<DependenciesStatusWire> {
    const config = getCurrentUserConfig();
    const [gitCheck, claudeCheck, piCheck] = await Promise.all([
      this.checkInstalled("GIT"),
      this.checkInstalled("CLAUDE"),
      this.checkInstalled("PI"),
    ]);

    const claudeMode = parseDependencyConfig(
      config.dependency_paths.claude,
    ).mode;
    const piMode = parseDependencyConfig(config.dependency_paths.pi).mode;
    const isAuthenticated = claudeCheck.installed
      ? await this.checkAuthenticated("CLAUDE")
      : null;

    const status: DependenciesStatusWire = {
      git: this.buildInfo("GIT", gitCheck, {}),
      claude: this.buildInfo("CLAUDE", claudeCheck, {
        mode: claudeMode,
        versionRange: rangeInfo(CLAUDE_VERSION_RANGE),
        isVersionInRange: claudeCheck.version
          ? isVersionInRange(claudeCheck.version, "CLAUDE")
          : null,
        managedVersion: getManagedVersion("CLAUDE"),
        isAuthenticated,
      }),
      pi: this.buildInfo("PI", piCheck, {
        mode: piMode,
        versionRange: rangeInfo(PI_VERSION_RANGE),
        isVersionInRange: piCheck.version
          ? isVersionInRange(piCheck.version, "PI")
          : null,
      }),
    };
    this.publish(status);
    return status;
  }

  // Publish dependencies_status to the bus; the projection dedups per connection
  // (streams.py L646-649), but skip republishing an identical object to keep the
  // bus quiet.
  private publish(status: DependenciesStatusWire): void {
    eventBus.publish({
      kind: "dependencies_status",
      status: status as unknown as Record<string, unknown>,
    });
  }

  async installManaged(tool: Dependency): Promise<InstallResultWire> {
    const managed = getManagedTool(tool);
    if (managed === undefined) {
      return {
        success: false,
        inProgress: false,
        version: null,
        path: null,
        error: `Installation not supported for tool: ${tool}`,
      };
    }
    if (this.stopRequested) {
      return {
        success: false,
        inProgress: false,
        version: null,
        path: null,
        error: "Service is shutting down",
      };
    }
    if (this.installing.has(tool)) {
      return {
        success: true,
        inProgress: true,
        version: null,
        path: null,
        error: null,
      };
    }
    let distribution: ResolvedDistribution;
    try {
      distribution = await this.resolveDistribution(managed);
    } catch (error) {
      return {
        success: false,
        inProgress: false,
        version: null,
        path: null,
        error: error instanceof Error ? error.message : String(error),
      };
    }
    if (this.installing.has(tool)) {
      return {
        success: true,
        inProgress: true,
        version: null,
        path: null,
        error: null,
      };
    }
    this.installing.add(tool);
    this.installError.delete(tool);
    this.installProgress.set(tool, {
      tool,
      bytesDownloaded: 0,
      totalBytes: distribution.size,
    });
    // Fire-and-forget: the download continues in the background and pushes
    // progress to observers; callers poll getStatus().
    void this.downloadVerifyStage(managed, distribution).finally(() => {
      this.installing.delete(tool);
      this.invalidateStatusCache();
      void this.getStatus();
    });
    return {
      success: true,
      inProgress: false,
      version: null,
      path: null,
      error: null,
    };
  }

  private async resolveDistribution(
    managed: ManagedToolDef,
  ): Promise<ResolvedDistribution> {
    const platformKey = managed.platformMap[currentPlatformLabel()];
    if (platformKey === undefined) {
      throw new Error(
        `Unsupported platform for managed ${managed.tool.toLowerCase()}: ${currentPlatformLabel()}`,
      );
    }
    if (managed.tool === "PI") {
      const pin = PI_PIN.platforms[platformKey];
      if (pin === undefined) {
        throw new Error(`Platform ${platformKey} not found in pin`);
      }
      return {
        version: PI_PIN.version,
        url: `${PI_RELEASE_BASE_URL}/v${PI_PIN.version}/${pin.asset}`,
        checksumSha256: pin.sha256,
        size: null,
        archive: "tarball",
        binarySubpath: "pi/pi",
      };
    }
    // Claude: fetch + adapt its GCP manifest.
    const manifestUrl = `${GCP_BUCKET_BASE_URL}/${CLAUDE_VERSION_RANGE.recommendedVersion}/manifest.json`;
    let manifest: {
      version: string;
      platforms: Record<
        string,
        { binary: string; checksum: string; size: number }
      >;
    };
    try {
      const response = await fetch(manifestUrl, {
        signal: AbortSignal.timeout(MANIFEST_FETCH_TIMEOUT_MS),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = (await response.json()) as {
        version: string;
        platforms: Record<
          string,
          { binary: string; checksum: string; size: number }
        >;
      };
      manifest = data;
    } catch (error) {
      throw new Error(
        `Failed to fetch manifest: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
    const platformInfo = manifest.platforms[platformKey];
    if (platformInfo === undefined) {
      throw new Error(`Platform ${platformKey} not found in manifest`);
    }
    return {
      version: manifest.version,
      url: `${GCP_BUCKET_BASE_URL}/${manifest.version}/${platformKey}/${platformInfo.binary}`,
      checksumSha256: platformInfo.checksum,
      size: platformInfo.size,
      archive: "single_binary",
      binarySubpath: platformInfo.binary,
    };
  }

  private async downloadVerifyStage(
    managed: ManagedToolDef,
    distribution: ResolvedDistribution,
  ): Promise<void> {
    const tool = managed.tool;
    const toolDir = getToolDir(tool);
    const tmpDir = path.join(
      toolDir,
      `tmp-${distribution.version}-${process.pid}`,
    );
    try {
      mkdirSync(tmpDir, { recursive: true });
      const downloadName =
        distribution.archive === "tarball"
          ? "download.tar.gz"
          : distribution.binarySubpath;
      const downloaded = path.join(tmpDir, downloadName);
      await this.download(distribution, downloaded, tool);

      const versionDir = path.join(
        toolDir,
        `${VERSION_DIR_PREFIX}${distribution.version}`,
      );
      const stagingDir = `${versionDir}.staging-${process.pid}`;
      rmSync(stagingDir, { recursive: true, force: true });
      mkdirSync(stagingDir, { recursive: true });

      if (distribution.archive === "tarball") {
        const extract = await runProcessToCompletion([
          "tar",
          "-xzf",
          downloaded,
          "-C",
          stagingDir,
        ]);
        if (extract.exitCode !== 0) {
          throw new Error(`Failed to extract archive: ${extract.stderr}`);
        }
      } else {
        renameSync(
          downloaded,
          path.join(stagingDir, distribution.binarySubpath),
        );
      }
      const stagedBinary = path.join(stagingDir, managed.binarySubpath);
      chmodSync(stagedBinary, 0o755);

      const probe = await runWithTimeout(
        [stagedBinary, "--version"],
        probeTimeoutMs(5_000),
      );
      if (probe.exitCode !== 0) {
        throw new Error("Installed binary failed its version check");
      }

      rmSync(versionDir, { recursive: true, force: true });
      renameSync(stagingDir, versionDir);
      this.cleanupOldVersions(tool, managed.retentionKeep);
      this.installError.delete(tool);
    } catch (error) {
      this.installError.set(
        tool,
        error instanceof Error ? error.message : String(error),
      );
    } finally {
      this.installProgress.delete(tool);
      rmSync(tmpDir, { recursive: true, force: true });
    }
  }

  private async download(
    distribution: ResolvedDistribution,
    dest: string,
    tool: Dependency,
  ): Promise<void> {
    const response = await fetch(distribution.url, {
      redirect: "follow",
      signal: AbortSignal.timeout(DOWNLOAD_CHUNK_TIMEOUT_MS),
    });
    if (!response.ok || response.body === null) {
      throw new Error(`Download failed: HTTP ${response.status}`);
    }
    const contentLength = response.headers.get("content-length");
    const totalBytes =
      distribution.size ??
      (contentLength !== null ? Number.parseInt(contentLength, 10) : null);
    const hash = createHash("sha256");
    let downloaded = 0;
    const fileStream = createWriteStream(dest);
    const sink = new Writable({
      write: (chunk: Buffer, _encoding, callback) => {
        hash.update(chunk);
        downloaded += chunk.length;
        this.installProgress.set(tool, {
          tool,
          bytesDownloaded: downloaded,
          totalBytes,
        });
        fileStream.write(chunk, () => callback());
      },
    });
    await response.body.pipeTo(Writable.toWeb(sink));
    await new Promise<void>((resolve, reject) =>
      fileStream.end((error?: Error | null) =>
        error ? reject(error) : resolve(),
      ),
    );
    const digest = hash.digest("hex");
    if (digest !== distribution.checksumSha256) {
      throw new Error("Checksum verification failed");
    }
  }

  private cleanupOldVersions(tool: Dependency, keep: number): void {
    const toolDir = getToolDir(tool);
    const versions = readdirSync(toolDir)
      .filter(isVersionDir)
      .map((name) => name.slice(VERSION_DIR_PREFIX.length))
      .sort((a, b) => compareVersions(b, a));
    for (const version of versions.slice(keep)) {
      rmSync(path.join(toolDir, `${VERSION_DIR_PREFIX}${version}`), {
        recursive: true,
        force: true,
      });
    }
  }

  // --- device-code auth (Claude only) --------------------------------------

  async startAuthLogin(tool: Dependency): Promise<AuthStartResultWire> {
    if (tool !== "CLAUDE") {
      return {
        authUrl: null,
        needsCode: false,
        success: false,
        error: `Authentication not supported for ${tool}`,
      };
    }
    const binary = resolveBinaryPath(tool);
    if (binary === null) {
      return {
        authUrl: null,
        needsCode: false,
        success: false,
        error: "Claude is not installed",
      };
    }
    const bg = spawnBackgroundProcess([binary, "auth", "login"]);
    const session = { process: bg, stdout: "", stderr: "" };
    this.authSession = session;
    let finished = false;
    let exitCode: number | null = null;
    bg.child.stdout?.on(
      "data",
      (chunk: Buffer) => (session.stdout += chunk.toString("utf8")),
    );
    bg.child.stderr?.on(
      "data",
      (chunk: Buffer) => (session.stderr += chunk.toString("utf8")),
    );
    bg.child.on("close", (code) => {
      finished = true;
      exitCode = code;
    });

    const authUrl = await this.awaitAuthUrl(session, () => finished);
    if (finished) {
      this.terminateAuthSession(session);
      return exitCode === 0
        ? { authUrl: null, needsCode: false, success: true, error: null }
        : {
            authUrl: null,
            needsCode: false,
            success: false,
            error: session.stderr || session.stdout || "Sign-in failed",
          };
    }
    if (authUrl === null) {
      this.terminateAuthSession(session);
      return {
        authUrl: null,
        needsCode: false,
        success: false,
        error: "Timed out waiting for the sign-in URL",
      };
    }
    return { authUrl, needsCode: true, success: false, error: null };
  }

  private async awaitAuthUrl(
    session: { stdout: string; stderr: string },
    isFinished: () => boolean,
  ): Promise<string | null> {
    const deadline = Date.now() + 30_000;
    for (;;) {
      if (isFinished()) {
        return null;
      }
      const match = /(https:\/\/\S+)/.exec(session.stdout + session.stderr);
      if (match) {
        return match[1] ?? null;
      }
      if (Date.now() >= deadline) {
        return null;
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
  }

  async submitAuthCode(
    tool: Dependency,
    code: string,
  ): Promise<AuthResultWire> {
    if (tool !== "CLAUDE") {
      return {
        success: false,
        authUrl: null,
        error: `Authentication not supported for ${tool}`,
      };
    }
    const session = this.authSession;
    if (session === null || session.process.child.exitCode !== null) {
      return {
        success: false,
        authUrl: null,
        error: "No sign-in is in progress. Start sign-in again.",
      };
    }
    this.authSession = null;
    try {
      session.process.child.stdin?.write(`${code.trim()}\n`);
      const exitCode = await this.waitForExit(session.process, 120_000);
      if (exitCode === 0) {
        // Auth state changed; re-probe on the next status read.
        this.invalidateStatusCache();
        return { success: true, authUrl: null, error: null };
      }
      return {
        success: false,
        authUrl: null,
        error: session.stderr || session.stdout || `Exit code ${exitCode}`,
      };
    } catch (error) {
      return {
        success: false,
        authUrl: null,
        error: error instanceof Error ? error.message : String(error),
      };
    } finally {
      this.terminateAuthSession(session);
    }
  }

  private waitForExit(
    bg: BackgroundProcess,
    timeoutMs: number,
  ): Promise<number | null> {
    return new Promise((resolve, reject) => {
      if (bg.child.exitCode !== null) {
        resolve(bg.child.exitCode);
        return;
      }
      const timer = setTimeout(() => {
        bg.child.kill("SIGKILL");
        reject(new Error("Authentication timed out"));
      }, timeoutMs);
      bg.child.on("close", (code) => {
        clearTimeout(timer);
        resolve(code);
      });
    });
  }

  private terminateAuthSession(session: { process: BackgroundProcess }): void {
    try {
      session.process.child.kill("SIGKILL");
    } catch {
      // already gone
    }
    if (this.authSession === session) {
      this.authSession = null;
    }
  }

  stop(): void {
    this.stopRequested = true;
  }
}

let singleton: DependencyService | undefined;

export function getDependencyService(): DependencyService {
  if (singleton === undefined) {
    singleton = new DependencyService();
  }
  return singleton;
}
