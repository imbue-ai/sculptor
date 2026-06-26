import type { PrState } from "~/services/pr_polling/status";

// Bounded scheduling for PR polling:
//   - at most WORKER_POOL_SIZE (4) polls in flight,
//   - a global minimum spacing (1.5 s) between successive CLI dispatches so
//     concurrent workers stagger their gh/glab calls,
//   - per-workspace poll delay from the user's interval (>= 10 s floor), backed
//     off for closed workspaces and terminal (merged/closed) PRs.

export const WORKER_POOL_SIZE = 4;
export const GLOBAL_MIN_POLL_SPACING_SECONDS = 1.5;
export const MIN_POLL_INTERVAL_SECONDS = 10;
export const TERMINAL_STATE_MULTIPLIER = 10;

export interface PollDelayConfig {
  pr_poll_interval_seconds: number;
  pr_poll_closed_multiplier: number;
}

export function computePollDelaySeconds(
  config: PollDelayConfig,
  isOpen: boolean,
  prState: PrState,
): number {
  const base = Math.max(
    config.pr_poll_interval_seconds,
    MIN_POLL_INTERVAL_SECONDS,
  );
  let multiplier = 1;
  if (!isOpen) {
    multiplier = Math.max(
      multiplier,
      Math.max(1, config.pr_poll_closed_multiplier),
    );
  }
  if (prState === "merged" || prState === "closed") {
    multiplier = Math.max(multiplier, TERMINAL_STATE_MULTIPLIER);
  }
  return base * multiplier;
}

export interface ThrottleDeps {
  now: () => number;
  sleep: (ms: number) => Promise<void>;
}

const realThrottleDeps: ThrottleDeps = {
  now: () => Date.now(),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
};

// Process-global throttle: successive acquire() resolutions are at least
// minIntervalMs apart, regardless of how many callers race for the slot.
export class PollSpacingThrottle {
  private nextAvailableAt = 0;

  constructor(
    private readonly minIntervalMs: number,
    private readonly deps: ThrottleDeps = realThrottleDeps,
  ) {}

  async acquire(): Promise<void> {
    const now = this.deps.now();
    const scheduledAt = Math.max(now, this.nextAvailableAt);
    this.nextAvailableAt = scheduledAt + this.minIntervalMs;
    const wait = scheduledAt - now;
    if (wait > 0) {
      await this.deps.sleep(wait);
    }
  }
}

// A minimal bounded-concurrency runner: at most `size` tasks run at once;
// the rest queue and start as slots free.
export class BoundedPool {
  private active = 0;
  private readonly waiters: Array<() => void> = [];

  constructor(private readonly size: number) {}

  async run<T>(task: () => Promise<T>): Promise<T> {
    // Re-check capacity after every wakeup: a freed slot can be claimed by a
    // fresh synchronous run() inside the wakeup microtask window, so a woken
    // waiter must not blindly take the slot or the cap could be exceeded. It
    // re-queues instead, and the next slot release wakes it again.
    while (this.active >= this.size) {
      await new Promise<void>((resolve) => this.waiters.push(resolve));
    }
    this.active += 1;
    try {
      return await task();
    } finally {
      this.active -= 1;
      this.waiters.shift()?.();
    }
  }

  get inFlight(): number {
    return this.active;
  }
}
