# Sculptor

[//]: # (<img src="images/sculptor-hero.png" width="70%">)

Build product with grounded, parallel coding agents.

Sculptor is a desktop app for running coding agents in parallel. Each task gets an isolated copy of your repo so agents can work side by side without merge chaos. The interface is clean, snappy, and modular. 

Open source, in active beta, and designed for teams willing to deploy early and share their feedback.

## Download
- [Mac (Apple Silicon)](https://tryimbue.link/sculptor-for-apple-silicon)
- [Linux](https://tryimbue.link/sculptor-for-linux)

**Getting started:** Connect a repo, create a workspace (an isolated copy of your code), and prompt an agent. Review the changes when it's done and merge back to main. To explore a different project, open another workspace. To collaborate with another agent on the same project, add one to the existing workspace.


## Feedback

[Open a GitHub issue](https://github.com/imbue-ai/sculptor/issues/new) for any bug, idea, or feedback.

Deploying Sculptor as a team? We open a private Slack channel for teams willing to share feedback in beta. Raise a GitHub issue to request access.


## See it in action

**Skills to ship faster:** The full library in one session: spec, mocks, and fix-bug across parallel workspaces. [Watch demo video.](https://www.loom.com/share/c9a9546122024844aeabff5b5a68514c)

**Fixing UI bugs fast:** `/sculptor:fix-bug` runs a short reproduction interview, writes failing tests, then makes them pass. Agents that ask before they answer. [Watch demo video.](https://www.loom.com/share/45ae363eb4fa40cfb04f5ade93754477)


## Skills

Reusable agent capabilities, callable as slash commands in any Sculptor session. They handle work you'd otherwise re-prompt for every time.

Some favorites:

A few favorites:

- **`/sculptor:write-spec`**: read your code, ask a few targeted questions, draft a spec grounded in your team's conventions.
- **`/sculptor:create-html-mock`**: generate a grid of HTML mock variants for a feature, ready to compare side by side in the browser.
- **`/sculptor:fix-bug`**: fix a bug with TDD. Sculptor runs a short reproduction interview, writes failing tests, then makes them pass.

Browse the [full set of slash commands and skills](https://github.com/imbue-ai/sculptor/blob/main/docs/slash-commands.md) with more coming soon.


## Docs

- [Workspaces](docs/workspaces.md): how they map to repos and how to create one
- [Agents](docs/agents.md): running multiple agents and complex tasks
- [Interface](docs/interface.md): chat, models, file refs, and terminal
- [Actions](docs/actions.md): saving prompts you use repeatedly
- [Changes](docs/changes.md): reviewing and committing agent changes
- [Slash Commands](docs/slash-commands.md): built-in commands and skills
- [Container Backend](docs/container-backend.md): running in a Docker or remote



## About Imbue

Sculptor is open source and built by [Imbue](https://imbue.com). We make tools that help people think, create, and build with code. We share our work openly because progress in AI should be collaborative and developer-driven, with agents that stay accountable to the people they serve.
