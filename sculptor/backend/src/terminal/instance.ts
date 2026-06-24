import { TerminalManager } from "~/terminal/manager";

// The process-wide terminal manager the WS/HTTP terminal routes share. A
// singleton because PTYs are long-lived OS processes that must survive across
// requests (a reconnecting xterm re-attaches to the same shell).

let manager: TerminalManager | undefined;

export function getTerminalManager(): TerminalManager {
  if (manager === undefined) {
    manager = new TerminalManager();
  }
  return manager;
}

export function resetTerminalManagerForTests(): void {
  manager?.closeAll();
  manager = undefined;
}
