// A small async concurrency limiter for bounded fan-out (e.g. promoting many
// QUEUED agents on cutover without spawning the whole fleet of subprocesses at
// once). The PR/CI bounded pool is separate (Task 7.1). No threads — just the
// event loop.
export class ConcurrencyLimiter {
  private active = 0;
  private readonly queue: (() => void)[] = [];

  constructor(private readonly limit: number) {
    if (limit < 1) {
      throw new Error("ConcurrencyLimiter limit must be >= 1");
    }
  }

  async run<T>(task: () => Promise<T>): Promise<T> {
    if (this.active >= this.limit) {
      await new Promise<void>((resolve) => this.queue.push(resolve));
    }
    this.active += 1;
    try {
      return await task();
    } finally {
      this.active -= 1;
      const next = this.queue.shift();
      if (next !== undefined) {
        next();
      }
    }
  }
}
