import { Theme } from "@radix-ui/themes";
import { usePluginSetting } from "@sculptor/plugin-sdk";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { DEFAULT_PROMPT_TEMPLATE, DEFAULT_TITLE_TEMPLATE } from "../linear/templates.ts";
import { LinearSettings } from "./LinearSettings.tsx";

// Mock only the SDK settings hook; the query client comes from a real provider
// so the API-key invalidation path runs for real.
vi.mock("@sculptor/plugin-sdk", () => ({ usePluginSetting: vi.fn() }));

// One mock setter per settings key, so each field's writes are observable
// independently of the others.
const setters = new Map<string, Mock>();
const setterFor = (key: string): Mock => {
  let setter = setters.get(key);
  if (!setter) {
    setter = vi.fn();
    setters.set(key, setter);
  }
  return setter;
};

beforeEach(() => {
  setters.clear();
  vi.mocked(usePluginSetting).mockImplementation((key: string) => ["", setterFor(key)]);
});
afterEach(() => cleanup());

const renderSettings = (): void => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Theme>
        <LinearSettings />
      </Theme>
    </QueryClientProvider>,
  );
};

describe("LinearSettings", () => {
  it("renders the API key field and the three template fields", () => {
    renderSettings();
    expect(screen.getByPlaceholderText("lin_api_...")).toBeTruthy();
    expect(screen.getByLabelText("Title")).toBeTruthy();
    expect(screen.getByLabelText("Branch")).toBeTruthy();
    expect(screen.getByLabelText("Prompt")).toBeTruthy();
  });

  it("shows each field's effective default as its placeholder", () => {
    renderSettings();
    expect((screen.getByLabelText("Title") as HTMLInputElement).placeholder).toBe(DEFAULT_TITLE_TEMPLATE);
    expect((screen.getByLabelText("Prompt") as HTMLTextAreaElement).placeholder).toBe(DEFAULT_PROMPT_TEMPLATE);
    // Branch has no template default — blank defers to the host's title-derived branch.
    expect((screen.getByLabelText("Branch") as HTMLInputElement).placeholder).toMatch(/derived from the title/i);
  });

  it("writes each template field to its own setting key", async () => {
    renderSettings();
    await userEvent.type(screen.getByLabelText("Title"), "T");
    await userEvent.type(screen.getByLabelText("Branch"), "B");
    await userEvent.type(screen.getByLabelText("Prompt"), "P");
    expect(setterFor("template:title")).toHaveBeenCalledWith("T");
    expect(setterFor("template:branch")).toHaveBeenCalledWith("B");
    expect(setterFor("template:prompt")).toHaveBeenCalledWith("P");
    expect(setterFor("apiKey")).not.toHaveBeenCalled();
  });

  it("writes the API key to its setting key without touching the templates", async () => {
    renderSettings();
    await userEvent.type(screen.getByPlaceholderText("lin_api_..."), "k");
    expect(setterFor("apiKey")).toHaveBeenCalledWith("k");
    expect(setterFor("template:title")).not.toHaveBeenCalled();
  });
});
