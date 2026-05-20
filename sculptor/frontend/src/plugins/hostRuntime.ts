import * as RadixThemes from "@radix-ui/themes";
import * as Jotai from "jotai";
import * as LucideReact from "lucide-react";
import * as React from "react";
import * as ReactJsxRuntime from "react/jsx-runtime";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";

import * as sdk from "./sdk/index.ts";

/**
 * Populates `window.__SCULPTOR_HOST__` with the singleton instances that
 * plugin runtime stubs (`public/plugin-runtime/*.js`) re-export. Must be
 * called once, before any plugin is loaded. Doing this in module scope
 * (rather than inside React) means the singletons are available as soon
 * as the host bundle finishes evaluating, which matches the lifetime the
 * plugin loader actually needs.
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
    radixThemes: RadixThemes,
    lucideReact: LucideReact,
    sdk,
  };
};
