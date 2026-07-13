import * as RadixThemes from "@radix-ui/themes";
import * as TanstackReactQuery from "@tanstack/react-query";
import * as Jotai from "jotai";
import * as LucideReact from "lucide-react";
import * as React from "react";
import * as ReactJsxRuntime from "react/jsx-runtime";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";
// Installed versions of the shared packages, embedded at build time by the
// extension-runtime-stubs Vite plugin (the same plugin that generates the stubs).
import { hostPackageVersions } from "virtual:sculptor/extension-host-versions";

import * as sdk from "./sdk/index.ts";

/**
 * Populates `window.__SCULPTOR_HOST__` with the singleton instances that the
 * generated extension runtime stubs (served at `/extension-runtime/*.js`) re-export.
 * Must be called once, before any extension is loaded. Doing this in module scope
 * (rather than inside React) means the singletons are available as soon
 * as the host bundle finishes evaluating, which matches the lifetime the
 * extension loader actually needs.
 *
 * `versions` carries the host's installed version of each shared package so the
 * loader can validate an extension manifest's declared peer ranges against reality.
 */
export const installHostRuntime = (): void => {
  if (typeof window === "undefined") return;
  if ((window as unknown as { __SCULPTOR_HOST__?: unknown }).__SCULPTOR_HOST__) return;

  (window as unknown as { __SCULPTOR_HOST__: unknown }).__SCULPTOR_HOST__ = {
    react: React,
    reactJsxRuntime: ReactJsxRuntime,
    reactDOM: ReactDOM,
    reactDOMClient: ReactDOMClient,
    jotai: Jotai,
    tanstackReactQuery: TanstackReactQuery,
    radixThemes: RadixThemes,
    lucideReact: LucideReact,
    sdk,
    versions: hostPackageVersions,
  };
};
