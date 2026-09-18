import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NamingConventionsResponse } from "~/api";
import { ElementIds, NamingConventionTier } from "~/api";

import { NamingConventionsRows } from "./NamingConventionsRows.tsx";

const apiHarness = vi.hoisted(() => ({
  getNamingConventions: vi.fn(),
  updateNamingConventions: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    getNamingConventions: apiHarness.getNamingConventions,
    updateNamingConventions: apiHarness.updateNamingConventions,
  };
});

const TEMPLATE = "# Naming conventions\n\nStarter text.\n";

const makeResponse = (): NamingConventionsResponse => ({
  globalFile: {
    tier: NamingConventionTier.USER,
    path: "/home/dev/.sculptor/naming.md",
    displayPath: "~/.sculptor/naming.md",
    content: "global rules",
  },
  projects: [
    {
      projectId: "proj_sculptor",
      projectName: "sculptor",
      projectPath: "~/code/sculptor",
      shared: {
        tier: NamingConventionTier.PROJECT,
        path: "/home/dev/code/sculptor/.sculptor/naming.md",
        displayPath: "~/code/sculptor/.sculptor/naming.md",
        content: "shared rules",
      },
      local: {
        tier: NamingConventionTier.LOCAL,
        path: "/home/dev/code/sculptor/.sculptor/naming.local.md",
        displayPath: "~/code/sculptor/.sculptor/naming.local.md",
        content: null,
      },
    },
  ],
  template: TEMPLATE,
});

const renderRows = async (): Promise<void> => {
  apiHarness.getNamingConventions.mockResolvedValue({ data: makeResponse() });
  render(
    <Theme>
      <NamingConventionsRows setToast={vi.fn()} />
    </Theme>,
  );
  await screen.findAllByTestId(ElementIds.SETTINGS_NAMING_CONVENTION_ROW);
};

const expandProjectRow = (): void => {
  fireEvent.click(screen.getAllByTestId(ElementIds.SETTINGS_NAMING_CONVENTION_ROW_TOGGLE)[1]);
};

const getTextareas = (): Array<HTMLTextAreaElement> =>
  screen.getAllByTestId(ElementIds.SETTINGS_NAMING_CONVENTION_TEXTAREA) as Array<HTMLTextAreaElement>;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("NamingConventionsRows", () => {
  it("lists the global file and one row per project, all collapsed", async () => {
    await renderRows();
    expect(screen.getAllByTestId(ElementIds.SETTINGS_NAMING_CONVENTION_ROW)).toHaveLength(2);
    expect(screen.queryAllByTestId(ElementIds.SETTINGS_NAMING_CONVENTION_TEXTAREA)).toHaveLength(0);
    expect(screen.getByText("sculptor")).toBeTruthy();
  });

  it("expands a project row into its shared and local editors", async () => {
    await renderRows();
    expandProjectRow();
    expect(getTextareas().map((textarea) => textarea.value)).toEqual(["shared rules", TEMPLATE]);
    expect(screen.getByText(".sculptor/naming.md")).toBeTruthy();
    expect(screen.getByText(".sculptor/naming.local.md")).toBeTruthy();
  });

  it("keeps the section with a retry when the list cannot be loaded", async () => {
    apiHarness.getNamingConventions.mockRejectedValueOnce(new Error("offline"));
    render(
      <Theme>
        <NamingConventionsRows setToast={vi.fn()} />
      </Theme>,
    );

    const retry = await screen.findByTestId(ElementIds.SETTINGS_NAMING_CONVENTIONS_RETRY);
    expect(screen.getByText("Naming conventions")).toBeTruthy();

    apiHarness.getNamingConventions.mockResolvedValue({ data: makeResponse() });
    fireEvent.click(retry);
    await screen.findAllByTestId(ElementIds.SETTINGS_NAMING_CONVENTION_ROW);
  });

  it("saves an edited local file when it loses focus", async () => {
    apiHarness.updateNamingConventions.mockResolvedValue({
      data: {
        tier: NamingConventionTier.LOCAL,
        path: "/home/dev/code/sculptor/.sculptor/naming.local.md",
        displayPath: "~/code/sculptor/.sculptor/naming.local.md",
        content: "my overrides",
      },
    });
    await renderRows();
    expandProjectRow();
    const [, local] = getTextareas();
    fireEvent.change(local, { target: { value: "my overrides" } });
    fireEvent.blur(local);
    await waitFor(() => expect(apiHarness.updateNamingConventions).toHaveBeenCalledTimes(1));
    expect(apiHarness.updateNamingConventions.mock.calls[0][0]).toMatchObject({
      body: { tier: NamingConventionTier.LOCAL, projectId: "proj_sculptor", content: "my overrides" },
    });
  });

  it("does not create a file when the untouched template loses focus", async () => {
    await renderRows();
    expandProjectRow();
    const [, local] = getTextareas();
    fireEvent.blur(local);
    expect(apiHarness.updateNamingConventions).not.toHaveBeenCalled();
  });
});
