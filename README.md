# Sculptor

Sculptor is a desktop app for running coding agents in parallel.

[Open a GitHub issue](https://github.com/imbue-ai/sculptor/issues/new) for any bug, idea, or feedback.

> [!NOTE]
> Sculptor is actively under development and should be treated as an experimental research preview. We are still learning what rigorous engineering looks like with agents.
>
> **What this means:**
>
> - Things will not be perfect. Expect mistakes and bugs.
> - Things may change quickly and significantly. We are optimizing for learning and may make drastic changes if we believe they lead to the best possible outcomes.
>
> That said, we use Sculptor extensively at Imbue ourselves, and put our best efforts towards ensuring it's useful and delightful.

---

> [!NOTE]
> At this time we don't have the bandwidth to take on a large volume of external contributions. We know it's not truly open source until the community is involved, and we're committed to embarking on that journey when we're truly ready. See [CONTRIBUTING.md](CONTRIBUTING.md) for how we handle issues and pull requests in the meantime.

## Download
- [Mac (Apple Silicon)](https://tryimbue.link/sculptor-for-apple-silicon)
- [Linux](https://tryimbue.link/sculptor-for-linux)

**Getting started:** Connect a repo, create a workspace (an isolated copy of your code), and prompt an agent. Review the changes when it's done and merge back to main. To explore a different project, open another workspace. To collaborate with another agent on the same project, add one to the existing workspace.

## A suite of skills for agentic development

Sculptor ships with a built-in selection of battle-tested skills that support agentic development workflows and help you
get the most out of your agents, your token budget and your attention.

**Skills to ship faster:** See our full library of skills in one session: spec, mocks, and fix-bug across parallel workspaces. [Watch demo video.](https://www.loom.com/share/c9a9546122024844aeabff5b5a68514c)

**Fixing UI bugs fast:** `/sculptor-workflow:fix-bug` runs a short reproduction interview, writes failing tests, then makes them pass. [Watch demo video.](https://www.loom.com/share/45ae363eb4fa40cfb04f5ade93754477)

## Your choice of agent harness

Our commitment to encouraging an open ecosystem of coding agents drives us to provide you with choices for integrating
agent harnesses. Sculptor ships with [integrated support](docs/help/integrated_harnesses.md) for the [Pi agentic
harness](https://pi.dev) in addition to Claude Code. Sculptor also allows you to run and manage _any_ terminal-based
agents.


## Docs

- [Getting Started](docs/help/getting_started.md): first-run setup and your first task
- [Workspaces](docs/help/workspaces.md): isolated worktrees of your repo, branches, and setup
- [Chat](docs/help/chat.md): the chat input, models, context, plan/effort, and mentions
- [Terminal](docs/help/terminal.md): the built-in terminal scoped to the workspace
- [Agents](docs/help/agents.md): running multiple agents and complex tasks
- [Integrated Harnesses](docs/help/integrated_harnesses.md): Sculptor's support for integrated harnesses
- [Changes](docs/help/changes.md): reviewing and committing agent changes
- [Pull Requests](docs/help/pull_requests.md): opening a GitHub PR and tracking its status
- [Skills](docs/help/skills.md): the bundled workflow and experimental skills
- [Command Palette](docs/help/command_palette.md): Cmd+K to search and jump around the app
- [Settings](docs/help/settings.md): a tour of the settings sections
- [Container Backend](docs/help/experimental/container_backend.md): running in Docker or on a remote (experimental)


## Running locally

For a quick local setup see the full details in [Getting Started](docs/development/getting_started.md).

## Why we made Sculptor

How we develop software is changing. Sculptor is our attempt to both understand that shift and help others follow us on the journey. We also strongly believe software development should stay open, and we want to live by that value. Ironically, without the industry's commitment to open source software, we wouldn't have the powerful agentic systems we have today. There's a strong desire among model providers to keep things closed, as it best serves their own interests — and their interests are not always aligned with ours.

We're also trying to develop at the frontier to understand what works and what doesn't. Our feeds are filled with hype, but they rarely delve into the nuance and tradeoffs. We have decades of experience building software systems and only a handful of years using LLMs to build them. The marketing pitches tell us AGI is around the corner; the reality is that it will take time for the world to adjust.

## About Imbue

Sculptor is open source and built by [Imbue](https://imbue.com). We make tools that help people think, create, and build with code. We share our work openly because progress in AI should be collaborative and developer-driven, with agents that stay accountable to the people they serve.
