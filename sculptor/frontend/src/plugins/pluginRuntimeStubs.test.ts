import type { Plugin } from "vite";
import { describe, expect, it } from "vitest";

import {
  collectHostVersions,
  collectStubs,
  HOST_VERSIONS_MODULE_ID,
  parseSdkValueExports,
  pluginRuntimeStubs,
  renderStub,
  renderVersionsModule,
  type RuntimeModuleConfig,
} from "../../vite-plugins/plugin-runtime-stubs.ts";

const keys = (entries: Record<string, ReadonlyArray<string>>): ReadonlyMap<string, ReadonlyArray<string>> =>
  new Map(Object.entries(entries));

/** Invoke a Vite hook that may be defined as a bare function or an object hook. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const callHook = (hook: unknown, ...args: ReadonlyArray<unknown>): any => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handler = typeof hook === "function" ? hook : (hook as any).handler;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (handler as (...a: ReadonlyArray<unknown>) => any)(...args);
};

describe("renderStub", () => {
  it("emits a default + sorted named exports for a single-source module", () => {
    const config: RuntimeModuleConfig = {
      file: "react.js",
      sources: [{ specifier: "react", hostKey: "react" }],
      defaultFrom: "react",
    };
    // Deliberately unsorted, and including the reserved `default` name.
    const out = renderStub(config, keys({ react: ["useState", "default", "Children"] }));

    expect(out).toContain("const host_react = host.react;");
    expect(out).toContain("export default host_react;");
    // `default` is never re-exported as a named binding.
    expect(out).not.toContain("export const default");
    // Named exports are sorted for byte-stability.
    expect(out.indexOf("export const Children")).toBeLessThan(out.indexOf("export const useState"));
    expect(out).toContain("export const useState = host_react.useState;");
    expect(out.endsWith("\n")).toBe(true);
  });

  it("is byte-stable regardless of the input key order", () => {
    const config: RuntimeModuleConfig = {
      file: "jotai.js",
      sources: [{ specifier: "jotai", hostKey: "jotai" }],
    };
    const a = renderStub(config, keys({ jotai: ["atom", "useAtom", "Provider"] }));
    const b = renderStub(config, keys({ jotai: ["Provider", "atom", "useAtom"] }));
    expect(a).toBe(b);
  });

  it("withholds excluded names but keeps the rest of the namespace", () => {
    const config: RuntimeModuleConfig = {
      file: "tanstack-react-query.js",
      sources: [{ specifier: "@tanstack/react-query", hostKey: "tanstackReactQuery" }],
      exclude: ["QueryClient", "QueryClientProvider"],
    };
    const out = renderStub(
      config,
      keys({ "@tanstack/react-query": ["useQuery", "QueryClient", "QueryClientProvider"] }),
    );
    expect(out).toContain("export const useQuery = host_tanstackReactQuery.useQuery;");
    expect(out).not.toContain("QueryClient");
    expect(out).not.toContain("QueryClientProvider");
  });

  it("emits a Proxy escape hatch as the default export", () => {
    const config: RuntimeModuleConfig = {
      file: "lucide-react.js",
      sources: [{ specifier: "lucide-react", hostKey: "lucideReact" }],
      proxyDefaultFrom: "lucideReact",
    };
    const out = renderStub(config, keys({ "lucide-react": ["Coins", "Hash"] }));
    expect(out).toContain("export default new Proxy(");
    expect(out).toContain("return host_lucideReact[key];");
    // Named icons are still enumerated so `import { Coins }` works too.
    expect(out).toContain("export const Coins = host_lucideReact.Coins;");
  });

  it("merges multiple sources with first-source-wins precedence", () => {
    const config: RuntimeModuleConfig = {
      file: "react-dom.js",
      sources: [
        { specifier: "react-dom/client", hostKey: "reactDOMClient" },
        { specifier: "react-dom", hostKey: "reactDOM" },
      ],
      defaultFrom: "reactDOM",
    };
    const out = renderStub(
      config,
      keys({
        "react-dom/client": ["createRoot", "hydrateRoot", "version"],
        "react-dom": ["createPortal", "flushSync", "version"],
      }),
    );
    // createRoot resolves to the client namespace (the react-dom re-export warns).
    expect(out).toContain("export const createRoot = host_reactDOMClient.createRoot;");
    expect(out).toContain("export const createPortal = host_reactDOM.createPortal;");
    expect(out).toContain("export default host_reactDOM;");
    // A name present in both sources is bound (and emitted) exactly once.
    expect(out.match(/export const version /g)).toHaveLength(1);
    expect(out).toContain("export const version = host_reactDOMClient.version;");
    // The guard names every required host key, so an absent one is reported.
    expect(out).toContain('const __missing = ["reactDOMClient","reactDOM"].filter');
  });

  it("skips names that are not valid identifiers or are reserved words", () => {
    const config: RuntimeModuleConfig = {
      file: "x.js",
      sources: [{ specifier: "x", hostKey: "x" }],
    };
    const out = renderStub(config, keys({ x: ["ok", "with-dash", "1bad", "delete", "class"] }));
    expect(out).toContain("export const ok = host_x.ok;");
    expect(out).not.toContain("with-dash");
    expect(out).not.toContain("1bad");
    // Reserved words would emit `export const delete = ...`, which won't parse.
    expect(out).not.toContain("export const delete");
    expect(out).not.toContain("export const class");
  });
});

describe("parseSdkValueExports", () => {
  it("collects value re-exports and drops type-only ones", () => {
    const source = [
      'export { PanelHeader } from "./components.ts";',
      'export { usePluginSetting, useWorkspaceBranch, useWorkspaceId, useWorkspaceTasks } from "./hooks.ts";',
      'export type { CodingAgentTaskView } from "~/api";',
    ].join("\n");
    expect(parseSdkValueExports(source)).toEqual([
      "PanelHeader",
      "usePluginSetting",
      "useWorkspaceBranch",
      "useWorkspaceId",
      "useWorkspaceTasks",
    ]);
  });

  it("handles inline type specifiers and aliases", () => {
    const source = 'export { value, type AType, original as renamed } from "./mod.ts";';
    expect(parseSdkValueExports(source)).toEqual(["renamed", "value"]);
  });
});

describe("pluginRuntimeStubs (host-versions virtual module)", () => {
  it("resolves and loads the virtual module with the real installed versions", async () => {
    const plugin: Plugin = pluginRuntimeStubs();
    // Point package resolution at this frontend project.
    callHook(plugin.configResolved, { root: process.cwd() });

    const resolved = callHook(plugin.resolveId, HOST_VERSIONS_MODULE_ID) as string;
    expect(resolved).toBe("\0" + HOST_VERSIONS_MODULE_ID);

    const code = (await callHook(plugin.load, resolved)) as string;
    expect(code).toContain("export const hostPackageVersions = Object.freeze({");
    // Reads each package's actual installed version (assert shape, not the exact
    // value, so a routine dep bump doesn't break the test).
    expect(code).toMatch(/"react":\s*"\d+\.\d+\.\d+"/);
    expect(code).toMatch(/"@radix-ui\/themes":\s*"\d+\.\d+\.\d+"/);
  });

  it("ignores unrelated module ids", () => {
    const plugin: Plugin = pluginRuntimeStubs();
    expect(callHook(plugin.resolveId, "some-other-module")).toBeUndefined();
  });
});

describe("collectStubs (real installed namespaces)", () => {
  // Exercises the namespace-reading path end to end: dynamic-imports the real
  // shared packages, reads the SDK barrel from source, and renders every stub.
  it("generates a stub per module with names from the real namespaces", async () => {
    const stubs = await collectStubs(process.cwd());

    // One stub per configured module (filenames the import map references).
    expect([...stubs.keys()].sort()).toEqual([
      "jotai.js",
      "lucide-react.js",
      "radix-themes.js",
      "react-dom.js",
      "react-jsx-runtime.js",
      "react.js",
      "sculptor-plugin-sdk.js",
      "tanstack-react-query.js",
    ]);

    // react: a representative hook from the actual namespace, plus the default.
    const react = stubs.get("react.js") as string;
    expect(react).toContain("export const useState = host_react.useState;");
    expect(react).toContain("export default host_react;");

    // tanstack: the deliberate API boundary holds against the real namespace.
    const tanstack = stubs.get("tanstack-react-query.js") as string;
    expect(tanstack).toContain("export const useQuery =");
    expect(tanstack).not.toContain("export const QueryClient ");
    expect(tanstack).not.toContain("export const QueryClientProvider ");

    // lucide: the Proxy escape hatch plus enumerated icons (thousands of them).
    const lucide = stubs.get("lucide-react.js") as string;
    expect(lucide).toContain("export default new Proxy(");
    expect((lucide.match(/^export const /gm) ?? []).length).toBeGreaterThan(1000);

    // SDK: names parsed from the first-party barrel, not an npm namespace.
    const sdk = stubs.get("sculptor-plugin-sdk.js") as string;
    expect(sdk).toContain("export const usePluginSetting = host_sdk.usePluginSetting;");
    expect(sdk).toContain("export const PanelHeader = host_sdk.PanelHeader;");
  });

  // A canary: well-known bindings every stub is expected to re-export. If a
  // package's namespace stops being read (rename, resolution change, the import
  // silently returning {}), these fail by name instead of surfacing as an
  // `undefined` import inside a plugin at runtime. Not exhaustive — full SDK
  // surface coverage belongs to plugin SDK testing — just an obvious tripwire.
  const WELL_KNOWN_EXPORTS: Record<string, ReadonlyArray<string>> = {
    "react.js": ["useState", "useEffect", "useMemo", "useRef", "useContext", "createContext", "forwardRef"],
    "react-jsx-runtime.js": ["jsx", "jsxs", "Fragment"],
    "react-dom.js": ["createPortal", "flushSync", "createRoot", "hydrateRoot"],
    "jotai.js": ["atom", "useAtom", "useAtomValue", "useSetAtom", "Provider"],
    "tanstack-react-query.js": ["useQuery", "useMutation", "useQueryClient", "useInfiniteQuery"],
    "radix-themes.js": ["Flex", "Box", "Text", "Button", "Card", "Dialog"],
    "lucide-react.js": ["Coins", "Hash", "Activity"],
    "sculptor-plugin-sdk.js": ["PanelHeader", "usePluginSetting", "useWorkspaceTasks"],
  };

  it("re-exports the well-known bindings of every module", async () => {
    const stubs = await collectStubs(process.cwd());
    for (const [file, names] of Object.entries(WELL_KNOWN_EXPORTS)) {
      const stub = stubs.get(file);
      expect(stub, `missing stub: ${file}`).toBeDefined();
      for (const name of names) {
        expect(stub, `${file} should export ${name}`).toContain(`export const ${name} = `);
      }
    }
  });

  it("is byte-stable across repeated runs", async () => {
    const a = await collectStubs(process.cwd());
    const b = await collectStubs(process.cwd());
    for (const [file, content] of a) expect(b.get(file)).toBe(content);
  });

  it("reads a real version for every embedded package", () => {
    const versions = collectHostVersions(process.cwd());
    for (const pkg of ["react", "react-dom", "jotai", "@tanstack/react-query", "@radix-ui/themes", "lucide-react"]) {
      expect(versions[pkg]).toMatch(/^\d+\.\d+\.\d+/);
    }
  });
});

describe("renderVersionsModule", () => {
  it("emits a sorted, frozen, byte-stable versions object", () => {
    const a = renderVersionsModule({ react: "18.3.1", jotai: "2.9.2" });
    const b = renderVersionsModule({ jotai: "2.9.2", react: "18.3.1" });
    expect(a).toBe(b);
    expect(a).toContain("export const hostPackageVersions = Object.freeze({");
    expect(a.indexOf('"jotai"')).toBeLessThan(a.indexOf('"react"'));
    expect(a).toContain('"react": "18.3.1",');
  });
});
