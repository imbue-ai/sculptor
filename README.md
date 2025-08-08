## What is Sculptor?

---

Sculptor is Imbue’s coding agent environment that allows you to run multiple coding agents simultaneously in safe,
isolated sandboxes. We’re currently beta testing Sculptor and are eager to hear what you think of it!

With Sculptor, you can:

- Run parallel agent tasks
- Interact with agents through an intuitive interface
- Work with your IDE of choice


## Installation & setup

---

<aside> 📣 **Recommended:** Join our [Discord](https://discord.gg/sBAVvHPUTE) community for dedicated support and up-to-date information from the Imbue team! </aside>

*Note: You will need an Anthropic API key and git repository to set up Sculptor.*

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and [mutagen](https://mutagen.io/documentation/introduction/installation/):

    ```bash
    brew install uv
    brew install mutagen-io/mutagen/mutagen
    ```

2. Install [Docker](https://www.docker.com/get-started/): [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/)
    1. Ensure your Docker version is 27 or higher according to `docker --version`
    2. Go to Settings > General > Virtual Machine Options after download and set “Virtual Machine Manager” to `Docker VMM`

3. Run Sculptor (insert your Anthropic API key and path to a git repository)

    ```bash
    ANTHROPIC_API_KEY=<your_key> uvx --with https://imbue-sculptor-latest.s3.us-west-2.amazonaws.com/sculptor.tar.gz --refresh sculptor <absolute_path_to_repo>
    ```

4. Configure your settings. As a beta tester, you will be opted in to send error logs and telemetry data. Let us know if this is an issue or if you need more information about this! 🙏

If you’re having trouble, [book time](https://calendly.com/nicseo/sculptor-chat) with us!


## Contributing

At this time, the best way to contribute to Sculptor is by being an active user of the tool and joining the community on [Discord](https://discord.gg/sBAVvHPUTE). Share your workflows, projects you've completed and your feedback with us.
