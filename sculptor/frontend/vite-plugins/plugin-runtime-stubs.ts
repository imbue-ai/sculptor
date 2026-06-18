import fs from "node:fs";
import path from "node:path";

import type { Plugin } from "vite";

/**
 * Generates the frontend plugin system's `/plugin-runtime/*.js` stubs at build
 * time instead of hand-maintaining them (SCU-1488).
 *
 * Each stub resolves a bare-specifier import in a plugin bundle (via the import
 * map in `index.html`) to the host's singleton instance of a shared package,
 * read from `window.__SCULPTOR_HOST__` (populated by `src/plugins/hostRuntime.ts`).
 * Hand-written stubs enumerated a curated subset of each package's exports, so a
 * plugin importing an un-listed name silently got `undefined` at runtime. Here we
 * derive the export list from the *actual* installed module namespace, so the
 * stub mirrors exactly what the host provides.
 *
 * The plugin serves the stubs from `/plugin-runtime/<file>` in dev and emits them
 * into the build output at the same path; `index.html`'s import map is unchanged.
 * It also exposes the host's installed package versions through a virtual module
 * (`virtual:sculptor/plugin-host-versions`) so the loader can later validate a
 * plugin manifest's declared peer ranges against the real versions.
 */

/** A package namespace merged into a stub, bound to its `window.__SCULPTOR_HOST__` key. */
type RuntimeSource = {
  /** Bare specifier whose installed namespace supplies the export names. */
  specifier: string;
  /** Key on `window.__SCULPTOR_HOST__` holding that namespace at runtime. */
  hostKey: string;
};

export type RuntimeModuleConfig = {
  /** Output filename under `/plugin-runtime/`. */
  file: string;
  /**
   * Namespaces merged into this stub, in precedence order: when the same name
   * appears in more than one source, the earliest source wins. (Used for
   * react-dom, where `createRoot`/`hydrateRoot` must bind to `react-dom/client`
   * rather than the deprecated re-exports on `react-dom`.)
   */
  sources: ReadonlyArray<RuntimeSource>;
  /** Emit `export default` as the namespace of this host key (e.g. `react`). */
  defaultFrom?: string;
  /**
   * Emit a `Proxy` default over this host key — an escape hatch that reaches any
   * member of the namespace without enumerating it. Used only for lucide-react,
   * whose ~5k icons are a low-risk, additive surface.
   */
  proxyDefaultFrom?: string;
  /**
   * Names deliberately withheld from plugins even though the namespace has them
   * (a real API boundary, not a curation shortcut). Documented per use below.
   */
  exclude?: ReadonlyArray<string>;
};

/** The SDK barrel is first-party, not an npm package; its names come from source. */
const SDK_SPECIFIER = "@sculptor/plugin-sdk";
const SDK_SOURCE_PATH = "src/plugins/sdk/index.ts";

const RUNTIME_MODULES: ReadonlyArray<RuntimeModuleConfig> = [
  { file: "react.js", sources: [{ specifier: "react", hostKey: "react" }], defaultFrom: "react" },
  {
    file: "react-jsx-runtime.js",
    sources: [{ specifier: "react/jsx-runtime", hostKey: "reactJsxRuntime" }],
  },
  {
    file: "react-dom.js",
    // client first so createRoot/hydrateRoot resolve to react-dom/client (the
    // top-level react-dom re-exports of those warn that they are deprecated).
    sources: [
      { specifier: "react-dom/client", hostKey: "reactDOMClient" },
      { specifier: "react-dom", hostKey: "reactDOM" },
    ],
    defaultFrom: "reactDOM",
  },
  { file: "jotai.js", sources: [{ specifier: "jotai", hostKey: "jotai" }] },
  {
    file: "tanstack-react-query.js",
    sources: [{ specifier: "@tanstack/react-query", hostKey: "tanstackReactQuery" }],
    // Plugins share the host's QueryClient (resolved via context — plugin panels
    // render under the host's QueryClientProvider). Withhold the means to build a
    // second one: a nested client would cut host components rendered inside a
    // plugin subtree off from the shared cache.
    exclude: ["QueryClient", "QueryClientProvider"],
  },
  { file: "radix-themes.js", sources: [{ specifier: "@radix-ui/themes", hostKey: "radixThemes" }] },
  {
    file: "lucide-react.js",
    sources: [{ specifier: "lucide-react", hostKey: "lucideReact" }],
    proxyDefaultFrom: "lucideReact",
  },
  { file: "sculptor-plugin-sdk.js", sources: [{ specifier: SDK_SPECIFIER, hostKey: "sdk" }] },
];

/**
 * The bare specifiers the import map resolves to host singletons — i.e. exactly
 * what a compiled plugin bundle must mark external so it shares the host's
 * instances instead of bundling its own copy. Derived from `RUNTIME_MODULES`
 * so a plugin build's externals can't drift from what the stubs provide.
 */
export const RUNTIME_MODULE_SPECIFIERS: ReadonlyArray<string> = [
  ...new Set(RUNTIME_MODULES.flatMap((module) => module.sources.map((source) => source.specifier))),
];

/** Packages whose installed versions are embedded for future manifest validation. */
const VERSION_PACKAGES: ReadonlyArray<string> = [
  "react",
  "react-dom",
  "jotai",
  "@tanstack/react-query",
  "@radix-ui/themes",
  "lucide-react",
];

export const HOST_VERSIONS_MODULE_ID = "virtual:sculptor/plugin-host-versions";
const RESOLVED_HOST_VERSIONS_MODULE_ID = "\0" + HOST_VERSIONS_MODULE_ID;

const GENERATED_HEADER =
  "// @generated by vite-plugins/plugin-runtime-stubs.ts (SCU-1488). DO NOT EDIT.\n" +
  "// Stub re-exporting the host's singleton from window.__SCULPTOR_HOST__.\n";

const IDENTIFIER_RE = /^[A-Za-z_$][A-Za-z0-9_$]*$/;

// Names that are valid-looking identifiers but illegal as an `export const`
// binding in a strict-mode ES module. A package is unlikely to export one, but
// if it did we'd emit a stub that fails to parse — skip them instead.
const RESERVED_NAMES: ReadonlySet<string> = new Set([
  "default",
  "arguments",
  "await",
  "break",
  "case",
  "catch",
  "class",
  "const",
  "continue",
  "debugger",
  "delete",
  "do",
  "else",
  "enum",
  "eval",
  "export",
  "extends",
  "false",
  "finally",
  "for",
  "function",
  "if",
  "implements",
  "import",
  "in",
  "instanceof",
  "interface",
  "let",
  "new",
  "null",
  "package",
  "private",
  "protected",
  "public",
  "return",
  "static",
  "super",
  "switch",
  "this",
  "throw",
  "true",
  "try",
  "typeof",
  "var",
  "void",
  "while",
  "with",
  "yield",
]);

/** A namespace member is re-exportable only as a valid, non-reserved identifier. */
const isExportableName = (name: string): boolean => !RESERVED_NAMES.has(name) && IDENTIFIER_RE.test(name);

const localBinding = (hostKey: string): string => `host_${hostKey}`;

/**
 * Render a single stub from the export names of each of its sources. Pure: the
 * caller supplies the resolved namespace keys so output is fully determined by
 * its inputs (and therefore byte-stable across builds with unchanged deps).
 */
export const renderStub = (
  config: RuntimeModuleConfig,
  keysBySpecifier: ReadonlyMap<string, ReadonlyArray<string>>,
): string => {
  const excluded = new Set(config.exclude ?? []);

  // Union of names across sources, sorted for byte-stability, each bound to the
  // first source that provides it (sources are in precedence order).
  const ownerByName = new Map<string, string>();
  for (const source of config.sources) {
    for (const name of keysBySpecifier.get(source.specifier) ?? []) {
      if (!isExportableName(name) || excluded.has(name)) continue;
      if (!ownerByName.has(name)) ownerByName.set(name, source.hostKey);
    }
  }

  const hostKeys = [...new Set(config.sources.map((s) => s.hostKey))];

  const lines: Array<string> = [GENERATED_HEADER + "const host = window.__SCULPTOR_HOST__;"];
  // Report every required key that is actually absent, not just the first one.
  lines.push(`const __missing = ${JSON.stringify(hostKeys)}.filter((k) => !host || !host[k]);`);
  lines.push("if (__missing.length) {");
  lines.push(
    '  throw new Error("Sculptor plugin runtime: window.__SCULPTOR_HOST__ missing " + __missing.join(", ") + ".");',
  );
  lines.push("}");
  for (const hostKey of hostKeys) lines.push(`const ${localBinding(hostKey)} = host.${hostKey};`);

  if (config.defaultFrom) {
    lines.push(`export default ${localBinding(config.defaultFrom)};`);
  } else if (config.proxyDefaultFrom) {
    // Reach any namespace member without enumerating it; see proxyDefaultFrom.
    const base = localBinding(config.proxyDefaultFrom);
    lines.push(
      "export default new Proxy(",
      "  {},",
      "  {",
      `    get(_, key) { return ${base}[key]; },`,
      `    has(_, key) { return key in ${base}; },`,
      `    ownKeys() { return Reflect.ownKeys(${base}); },`,
      `    getOwnPropertyDescriptor(_, key) { return Reflect.getOwnPropertyDescriptor(${base}, key); },`,
      "  },",
      ");",
    );
  }

  for (const name of [...ownerByName.keys()].sort()) {
    const base = localBinding(ownerByName.get(name) as string);
    lines.push(`export const ${name} = ${base}.${name};`);
  }

  return lines.join("\n") + "\n";
};

/** Render the embedded host-versions virtual module. Pure and byte-stable. */
export const renderVersionsModule = (versions: Readonly<Record<string, string>>): string => {
  const entries = Object.keys(versions)
    .sort()
    .map((name) => `  ${JSON.stringify(name)}: ${JSON.stringify(versions[name])},`);
  return (
    "// @generated by vite-plugins/plugin-runtime-stubs.ts (SCU-1488). DO NOT EDIT.\n" +
    "export const hostPackageVersions = Object.freeze({\n" +
    entries.join("\n") +
    "\n});\n"
  );
};

/**
 * Extract the value (non-type) export names from the SDK barrel source. The
 * barrel is a controlled re-export file, so a focused parse is enough and avoids
 * executing its browser-only imports just to read names.
 */
export const parseSdkValueExports = (source: string): Array<string> => {
  const names = new Set<string>();
  const blockRe = /export\s+(type\s+)?\{([^}]*)\}/g;
  let match: RegExpExecArray | null;
  while ((match = blockRe.exec(source)) !== null) {
    if (match[1]) continue; // whole-statement `export type { ... }`
    for (const raw of match[2].split(",")) {
      const spec = raw.trim();
      if (!spec || spec.startsWith("type ")) continue; // inline `type X`
      // `A as B` re-exports under B.
      const exported = spec.split(/\s+as\s+/).pop() as string;
      if (isExportableName(exported)) names.add(exported);
    }
  }
  return [...names].sort();
};

const readInstalledVersion = (root: string, pkg: string): string => {
  const manifestPath = path.join(root, "node_modules", pkg, "package.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8")) as { version?: string };
  if (typeof manifest.version !== "string") {
    throw new Error(`plugin-runtime-stubs: no version for "${pkg}" at ${manifestPath}`);
  }
  return manifest.version;
};

/** Read the installed version of every embedded package, resolved under `root`. */
export const collectHostVersions = (root: string): Record<string, string> => {
  const versions: Record<string, string> = {};
  for (const pkg of VERSION_PACKAGES) versions[pkg] = readInstalledVersion(root, pkg);
  return versions;
};

/**
 * Generate every stub's content, keyed by output filename. Reads each shared
 * package's actual installed namespace (and the first-party SDK barrel from
 * source), resolved under `root`. This is the build-time path the dev
 * middleware and `generateBundle` both rely on.
 */
export const collectStubs = async (root: string): Promise<Map<string, string>> => {
  // Resolve each distinct specifier's namespace once. npm packages come from
  // their installed ESM namespace; the first-party SDK barrel from source.
  const specifiers = new Set(RUNTIME_MODULES.flatMap((m) => m.sources.map((s) => s.specifier)));
  const keysBySpecifier = new Map<string, ReadonlyArray<string>>();
  for (const specifier of specifiers) {
    if (specifier === SDK_SPECIFIER) {
      const source = fs.readFileSync(path.join(root, SDK_SOURCE_PATH), "utf8");
      keysBySpecifier.set(specifier, parseSdkValueExports(source));
    } else {
      const namespace = (await import(specifier)) as Record<string, unknown>;
      keysBySpecifier.set(specifier, Object.keys(namespace));
    }
  }
  const stubs = new Map<string, string>();
  for (const config of RUNTIME_MODULES) stubs.set(config.file, renderStub(config, keysBySpecifier));
  return stubs;
};

export const pluginRuntimeStubs = (): Plugin => {
  let root = process.cwd();
  let stubsPromise: Promise<Map<string, string>> | null = null;
  let versionsPromise: Promise<Record<string, string>> | null = null;

  const ensureVersions = (): Promise<Record<string, string>> =>
    (versionsPromise ??= Promise.resolve().then(() => collectHostVersions(root)));
  const ensureStubs = (): Promise<Map<string, string>> => (stubsPromise ??= collectStubs(root));

  return {
    name: "sculptor:plugin-runtime-stubs",

    configResolved(config): void {
      root = config.root;
    },

    resolveId(id): string | undefined {
      return id === HOST_VERSIONS_MODULE_ID ? RESOLVED_HOST_VERSIONS_MODULE_ID : undefined;
    },

    async load(id): Promise<string | undefined> {
      if (id !== RESOLVED_HOST_VERSIONS_MODULE_ID) return undefined;
      return renderVersionsModule(await ensureVersions());
    },

    configureServer(server): void {
      server.middlewares.use((req, res, next) => {
        const url = (req.url ?? "").split("?")[0];
        const match = url.match(/^\/plugin-runtime\/([\w.-]+\.js)$/);
        if (!match) {
          next();
          return;
        }
        void ensureStubs().then((stubs) => {
          const content = stubs.get(match[1]);
          if (content === undefined) {
            next();
            return;
          }
          res.setHeader("Content-Type", "text/javascript; charset=utf-8");
          // Regenerated per dev server start; never let the browser pin a stale copy.
          res.setHeader("Cache-Control", "no-cache");
          res.end(content);
        }, next);
      });
    },

    async generateBundle(): Promise<void> {
      const stubs = await ensureStubs();
      for (const [file, source] of stubs) {
        // Explicit fileName (not assetFileNames) keeps the path the import map
        // references — /plugin-runtime/<file> — stable and unhashed.
        this.emitFile({ type: "asset", fileName: `plugin-runtime/${file}`, source });
      }
    },
  };
};
