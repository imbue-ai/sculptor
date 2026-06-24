import { describe, expect, it } from "vitest";

import {
  classifyCliError,
  CliStatusError,
  type CliRunner,
} from "~/services/pr_polling/cli_status";
import {
  BoundedPool,
  computePollDelaySeconds,
  PollSpacingThrottle,
} from "~/services/pr_polling/pool";
import { detectProvider } from "~/services/pr_polling/provider";
import { fetchPrStatus } from "~/services/pr_polling/status";

describe("detectProvider", () => {
  it("recognizes GitHub and GitLab over SSH and HTTPS", () => {
    expect(detectProvider("git@github.com:owner/repo.git")).toBe("github");
    expect(detectProvider("https://github.com/owner/repo.git")).toBe("github");
    expect(detectProvider("ssh://git@gitlab.com/owner/repo.git")).toBe(
      "gitlab",
    );
    expect(detectProvider("https://gitlab.example.com/owner/repo.git")).toBe(
      "gitlab",
    );
    expect(detectProvider("git@bitbucket.org:owner/repo.git")).toBeNull();
    expect(detectProvider(null)).toBeNull();
  });
});

describe("classifyCliError (REQ-INT-003 taxonomy stays distinct)", () => {
  it("maps stderr to the right category", () => {
    expect(classifyCliError("API rate limit exceeded")).toBe("rate_limited");
    expect(classifyCliError("error: not logged into any GitHub hosts")).toBe(
      "not_authenticated",
    );
    expect(classifyCliError("HTTP 401 Unauthorized")).toBe("not_authenticated");
    expect(classifyCliError("HTTP 403: Forbidden")).toBe("no_access");
    expect(classifyCliError("could not resolve host: github.com")).toBe(
      "network_error",
    );
    expect(classifyCliError("HTTP 503 Service Unavailable")).toBe("transient");
    expect(classifyCliError("unknown JSON field: foo")).toBe("transient");
  });
});

describe("computePollDelaySeconds (REQ-NFR-060)", () => {
  const config = { pr_poll_interval_seconds: 30, pr_poll_closed_multiplier: 6 };
  it("applies the floor, closed multiplier, and terminal backoff", () => {
    expect(computePollDelaySeconds(config, true, "open")).toBe(30);
    expect(
      computePollDelaySeconds(
        { ...config, pr_poll_interval_seconds: 5 },
        true,
        "open",
      ),
    ).toBe(10);
    expect(computePollDelaySeconds(config, false, "open")).toBe(180);
    expect(computePollDelaySeconds(config, true, "merged")).toBe(300);
  });
});

describe("PollSpacingThrottle (REQ-NFR-011 global 1.5s spacing)", () => {
  it("spaces successive acquisitions by the min interval", async () => {
    let clock = 0;
    const sleeps: number[] = [];
    const throttle = new PollSpacingThrottle(1500, {
      now: () => clock,
      sleep: async (ms) => {
        sleeps.push(ms);
        clock += ms;
      },
    });
    await throttle.acquire();
    await throttle.acquire();
    await throttle.acquire();
    expect(sleeps).toEqual([1500, 1500]);
  });
});

describe("BoundedPool (REQ-NFR-011 max 4 workers)", () => {
  it("never runs more than the configured number concurrently", async () => {
    const pool = new BoundedPool(4);
    let peak = 0;
    const release: Array<() => void> = [];
    const tasks = Array.from({ length: 8 }, () =>
      pool.run(async () => {
        peak = Math.max(peak, pool.inFlight);
        await new Promise<void>((resolve) => release.push(resolve));
      }),
    );
    // Let the first wave start, then drain.
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(pool.inFlight).toBeLessThanOrEqual(4);
    while (release.length > 0) {
      release.shift()?.();
      await new Promise((resolve) => setTimeout(resolve, 1));
    }
    await Promise.all(tasks);
    expect(peak).toBeLessThanOrEqual(4);
  });
});

describe("fetchPrStatus", () => {
  const okRunner =
    (stdout: string): CliRunner =>
    async () => ({ code: 0, stdout, stderr: "" });

  it("maps a GitHub open PR with a passing pipeline", async () => {
    const runner = okRunner(
      JSON.stringify([
        {
          number: 5,
          title: "Add feature",
          url: "https://x/pr/5",
          state: "OPEN",
          mergeable: "MERGEABLE",
          statusCheckRollup: [{ state: "SUCCESS" }],
        },
      ]),
    );
    const status = await fetchPrStatus(
      "github",
      "ws_1",
      "feat",
      "/tmp",
      runner,
    );
    expect(status.pr_state).toBe("open");
    expect(status.pr_iid).toBe(5);
    expect(status.pipeline_status).toBe("passed");
    expect(status.has_conflicts).toBe(false);
  });

  it("returns pr_state none when there is no PR", async () => {
    const status = await fetchPrStatus(
      "github",
      "ws_1",
      "feat",
      "/tmp",
      okRunner("[]"),
    );
    expect(status.pr_state).toBe("none");
    expect(status.error_category).toBeUndefined();
  });

  it("surfaces cli_missing distinctly", async () => {
    const runner: CliRunner = async () => {
      throw new CliStatusError("cli_missing", "gh not found");
    };
    const status = await fetchPrStatus(
      "github",
      "ws_1",
      "feat",
      "/tmp",
      runner,
    );
    expect(status.error_category).toBe("cli_missing");
    expect(status.error_provider).toBe("github");
  });

  it("surfaces a rate limit distinctly", async () => {
    const runner: CliRunner = async () => ({
      code: 1,
      stdout: "",
      stderr: "API rate limit exceeded",
    });
    const status = await fetchPrStatus(
      "github",
      "ws_1",
      "feat",
      "/tmp",
      runner,
    );
    expect(status.error_category).toBe("rate_limited");
  });
});
