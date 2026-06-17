import { describe, expect, it } from "vitest";

import {
  parseSdkValueExports,
  renderStub,
  renderVersionsModule,
  type RuntimeModuleConfig,
} from "../../vite-plugins/plugin-runtime-stubs.ts";

const keys = (entries: Record<string, ReadonlyArray<string>>): ReadonlyMap<string, ReadonlyArray<string>> =>
  new Map(Object.entries(entries));

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
    // The guard checks every host key the stub depends on.
    expect(out).toContain("if (!host || !host.reactDOMClient || !host.reactDOM) {");
  });

  it("skips names that are not valid identifiers", () => {
    const config: RuntimeModuleConfig = {
      file: "x.js",
      sources: [{ specifier: "x", hostKey: "x" }],
    };
    const out = renderStub(config, keys({ x: ["ok", "with-dash", "1bad"] }));
    expect(out).toContain("export const ok = host_x.ok;");
    expect(out).not.toContain("with-dash");
    expect(out).not.toContain("1bad");
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
