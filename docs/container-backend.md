# Running the Backend in a Container

Sculptor supports running the backend as a separate process via a **custom backend command**. This lets you run the backend in an environment that differs from your host OS — for example, inside a Docker container, on a remote server over SSH, or in a VM.

This guide walks through a Docker container recipe as a starting point. The same approach generalizes to other configurations; we plan to share more recipes in the future.

---

## Overview

The Sculptor desktop app can spawn a user-provided shell command instead of using its built-in backend. The command prints a URL to stdout, and the app connects to it. Everything else — the UI, workspace management, agent orchestration — stays the same.

The [container recipe gist](https://gist.github.com/sgeisenh/a7576dab2bd94884af3b1e43a92b8f7f) provides a working Docker setup that:

1. Builds a container image with git, Claude CLI, and runtime dependencies
2. Auto-downloads the Sculptor backend binaries on first start
3. Prints the backend URL so the desktop app can connect
4. Forwards signals cleanly so the container shuts down when you close Sculptor

---

## Prerequisites

You'll need three things installed on your host machine:

- **Python 3.10+** — the launcher script (`run-backend.py`) is a Python program
- **Docker** (or a compatible container engine) — must support volumes for persistent state
- **Sculptor** — the desktop app itself

---

## Setup

### 1. Clone the recipe

```bash
git clone https://gist.github.com/sgeisenh/a7576dab2bd94884af3b1e43a92b8f7f sculptor-docker
cd sculptor-docker
```

### 2. Configure the custom backend command

Open Sculptor, then go to **Settings > Experimental** and set the **Custom Backend Command** to the full path of the launcher script:

```
/full/path/to/sculptor-docker/run-backend.py
```

### 3. Restart Sculptor

On first launch, the launcher will:

1. Build the Docker image (cached on subsequent starts)
2. Start the container and download the latest backend binaries (~100 MB, cached after the first time)
3. Connect the desktop app to the containerized backend

Subsequent starts are fast since both the image and binaries are cached.

---

## Onboarding quirks

There are a few rough edges in the current setup to be aware of.

### Entering personal information multiple times

Sculptor will ask for your name and email twice during initial setup — once for the local backend and once for the in-container backend. This is expected.

### Authenticating Claude on macOS

If your host OS is macOS, Claude Code stores credentials in the system keychain, which isn't accessible from inside the container. You'll need to authenticate `claude` within the container environment:

1. Open a terminal inside the running container
2. Run `claude` to start the initial setup flow
3. The setup will display an authentication URL — **copy this URL into a text editor first** to remove newlines that `claude` inserts when rendering the line-wrapped URL, then paste the cleaned-up URL into your browser

### Restarting Sculptor after configuration changes

Sculptor must be manually restarted whenever you set or clear the custom backend command. Closing and reopening the app is sufficient.

### Using the built-in workspace

The container comes with an empty git repository at `/workspace/` that you can use as a scratch project if you want to get started quickly without cloning a repo.

---

## Exploring the recipe

The gist contains configuration options (environment variables for ports, volumes, binary sources, etc.) and troubleshooting tips. You can read through the gist's README and scripts directly, or point an agent at the cloned recipe to explore and customize it for your setup.

---

## Beyond Docker: other configurations

The container recipe is a **starting point** that demonstrates how the custom backend command works. The same mechanism supports many other configurations — for example, connecting to a backend running on a remote server over SSH or in a cloud VM. We're planning to share more recipes for these setups in the future.

We encourage you to experiment with using an agent to iterate on the custom backend command to best suit your needs. The container gist serves as a useful reference for how to download the backend binaries and what the backend process expects (bind address, port, signal handling, etc.).

---

## Known limitations

We're actively working to improve this experience. In particular:

- **macOS authentication** — We plan to improve the story for forwarding credentials from macOS hosts so that the manual `claude` auth step is no longer needed.
- **Repeated identity prompts** — We're looking into ways to reduce the number of times you need to enter personal information.
- **Manual restarts required** — We plan to provide a mechanism to choose from several custom backend commands without requiring a full restart of the app.

> **Note:** The custom backend command is an unstable feature and the backend interface is subject to change. The gist and this guide will be updated as the interface evolves.
