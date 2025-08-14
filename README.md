# Sculptor: run parallel Claude Code agents in safe, local sandboxes

Sculptor lets you run simultaneous Claude Code agents in safe, isolated sandboxes. Sculptor runs locally, letting you iterate quickly in your chosen IDE without going through PRs. We’re currently alpha testing Sculptor and are excited to hear what you think!

### Kick off agents in parallel

Sculptor is a web UI for creating and managing multiple agents. Each agent runs in its own isolated sandbox with a clone of your repo, so you can experiment and make changes safely. Desktop app coming soon!

### Test & edit agent changes locally

Sync to any agent’s sandbox to instantly see its file changes in your local IDE. This lets you review, run, test, and edit the agent’s changes in your local environment while it's working in a sandbox, giving you the best of both worlds.

### Easily merge changes & resolve conflicts

Quickly merge the agent branches that you like. Sculptor agents can help you resolve any merge conflicts that arise.

### See the power of Sculptor in this behind-the-scenes demo 🤓
See it all come together in this behind-the-scenes demo from one of our product engineers, Guinness:

[![A demo of what is possible with Sculptor](https://img.youtube.com/vi/ESZH7hd1sMY/0.jpg)](https://www.youtube.com/watch?v=ESZH7hd1sMY)

Sculptor is built by [Imbue](https://imbue.com).

# Installation & setup
> [!IMPORTANT]
> Join our [Discord](https://discord.gg/sBAVvHPUTE) for dedicated support and up-to-date info from the Imbue team! Our whole team's in Discord with you, building Sculptor with Sculptor 🙂

### 1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and [mutagen](https://mutagen.io/documentation/introduction/installation/):

**Via Homebrew (Mac or Linux)**:

```bash
brew install uv
brew install mutagen-io/mutagen/mutagen
```

**On Linux**:

```bash
pipx install uv # OR pip install uv
```

Install the [appropriate latest released binary for Mutagen](https://github.com/mutagen-io/mutagen/releases)


### 2. Install [Docker](https://www.docker.com/get-started/):

**On Mac**:
[Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/)

- Ensure your Docker version is 27 or higher according to `docker --version`
- Go to Settings > General > Virtual Machine Options after download and set “Virtual Machine Manager” to `Docker VMM`

**On Linux**:
Do *not* install Docker Desktop.

- Instead, install Docker Engine by [following the instructions here](https://docs.docker.com/engine/install/)


### 3. Run Sculptor
*Note: You'll need an Anthropic API key and git repository to use Sculptor.*

```bash
# Change directory to your code repository
cd /to/your/repo

# Run Sculptor
uvx --with https://imbue-sculptor-latest.s3.us-west-2.amazonaws.com/sculptor.tar.gz --refresh sculptor .
```

### 4. Configure your settings
As a beta tester, you'll be opted in to send error logs and telemetry data. Let us know if this is an issue or if you need more information about this! 🙏


# Community
### Discord

As an early tester, we highly recommend that you join our [Discord](https://discord.gg/sBAVvHPUTE) community to get direct support from the Imbue team. Some interesting channels:

- `#bugs-and-support`: Get quick support from the Imbue team
- `#behind-the-scenes`: Watch how the sausage gets made as our team uses Sculptor to build Sculptor
- `#show-and-tell`: See what other people have created with Sculptor, and share your own Sculptures

### Talk with us

We’re always here for you! If you run into any issues or just want to chat with the team, [book time](https://calendly.com/nicseo/sculptor-chat) with us!

# License
© Imbue, Inc. All rights reserved. Use is subject to Imbue's [Research Preview Terms of Service](https://imbue.com/terms/).
