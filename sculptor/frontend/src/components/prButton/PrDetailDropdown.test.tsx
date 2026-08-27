import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it } from "vitest";

import type { PrStatusInfo } from "~/api";
import { reusableTabTarget } from "~/common/reusableTabTarget.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { PrDetailDropdown } from "./PrDetailDropdown.tsx";

const WORKSPACE_ID = "ws-pr-1";
const PR_URL = "https://github.com/imbue-ai/sculptor/pull/392";
const PIPELINE_URL = "https://github.com/imbue-ai/sculptor/actions/runs/12345";

const prStatus = (overrides: Partial<PrStatusInfo>): PrStatusInfo => ({
  workspaceId: WORKSPACE_ID,
  prState: "open",
  prIid: 392,
  prTitle: "Reuse browser tabs for PR links",
  prWebUrl: PR_URL,
  pipelineStatus: "passed",
  pipelineId: 12345,
  pipelineWebUrl: PIPELINE_URL,
  ...overrides,
});

afterEach(() => {
  cleanup();
});

describe("PrDetailDropdown links target reusable tabs", () => {
  it("points the PR title link at the PR's reusable tab, not _blank", () => {
    renderWithProviders(<PrDetailDropdown prStatus={prStatus({})} />, { store: createStore() });

    const prLink = screen.getByRole("link", { name: /Reuse browser tabs for PR links/ });
    expect(prLink).toHaveAttribute("target", reusableTabTarget(PR_URL));
    expect(prLink).not.toHaveAttribute("target", "_blank");
  });

  it("points the pipeline link at its own reusable tab, distinct from the PR tab", () => {
    renderWithProviders(<PrDetailDropdown prStatus={prStatus({})} />, { store: createStore() });

    const pipelineLink = screen.getByRole("link", { name: "#12345" });
    expect(pipelineLink).toHaveAttribute("target", reusableTabTarget(PIPELINE_URL));
    expect(reusableTabTarget(PIPELINE_URL)).not.toBe(reusableTabTarget(PR_URL));
  });
});
