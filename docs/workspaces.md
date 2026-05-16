# Workspaces

A workspace is a project environment in Sculptor. Each workspace is tied to one repository. When you create a workspace, Sculptor clones that repo into its own directory and runs all agents against the clone.

---

## How workspaces map to repos

When you create a workspace, Sculptor:

1. Clones the target repository into `~/.sculptor/workspaces/<workspace-id>/code/`
2. Checks out the source branch you chose on a fresh workspace branch
3. Runs all agents in that cloned environment

This means your original repo is never touched directly. Changes the agent makes live in the workspace clone until you explicitly commit them.

The repo and branch are shown in the top bar of the Sculptor window:

![Repo and branch shown in the top bar](../images/workspace-path.png)

For a workspace cloned from a repo called `api-server` off the `main` branch, the top bar reads `api-server › main`. Click the repo name to open a dropdown with **Open folder**, **Copy relative path**, **Copy path**, and one entry per app you have installed for opening the directory (your editor, your terminal, and so on). Click the branch name to copy it to your clipboard.

---

## Creating a workspace

Click the **+** button at the top of the Sculptor window to open the new-workspace form. Choose a repository by URL or local path, pick a source branch, and (optionally) give the workspace a name and a starter prompt. Sculptor clones the repo and spins up the first agent.

Each workspace tab is independent, so switching between tabs switches between different repos and their agent sessions.

---

## Multiple workspaces

You can have multiple workspaces open at once, one per tab. Each workspace maintains its own:

- Cloned repository state
- Active agents and their conversation histories
- Pending code changes

There's no shared state between workspaces.

---

## Where the data lives

Sculptor stores workspace data under `~/.sculptor/workspaces/` on your home directory. Each workspace is a self-contained directory keyed by an internal ID, with the repo clone at `code/` plus Sculptor metadata alongside it.

You can open a terminal inside Sculptor (see [Interface](interface.md)) to inspect or interact with the workspace clone directly.
