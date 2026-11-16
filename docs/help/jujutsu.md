# Jujutsu (jj)

[Jujutsu](https://jj-vcs.github.io/jj/latest/) (jj) is a version control system
that keeps its history in a git repository. Sculptor can give a repository's new
workspaces a **jj workspace** instead of a git worktree, so you and your agents
work on that repository with jj.

jj is optional. A repository uses it only after you turn it on for that
repository, and Sculptor needs no jj for any other repository.

---

## How a jj workspace differs from a worktree

A worktree workspace is a second git checkout on a branch of its own. A jj
workspace is jj's equivalent: a second working copy of the same jj repository,
made with `jj workspace add`. It shares the repository's history, so revisions
an agent makes there show up in `jj log` in your own checkout.

What changes for you:

- **There is no git inside it.** The workspace directory holds a `.jj` and no
  `.git`, so `git` commands fail there. Use `jj` in its terminal, as the agents
  do. The top bar shows a **jj** badge to remind you.
- **Git hooks don't run in it.**
- **Its name is a bookmark, not a branch.** A bookmark is jj's name for a
  revision. Pushing a bookmark creates or updates the branch of the same name on
  the remote.
- **The working copy is a revision.** Every jj command first records your file
  changes into the working-copy revision. There is no staging area.

A workspace keeps the kind it was created with. Turning jj off for a repository
changes only the workspaces you create after that.

Claude and Pi agents in a jj workspace are told that git fails there and how to
work with jj, and are asked to use the bundled jj skill before any
version-control command. Terminal agents get no such instructions.

---

## Setting up jj

Open **Settings > Jujutsu**. The callout at the top says whether Sculptor can use
jj, and if not, what is wrong and how to fix it. Click **Re-check** after you
change something outside Sculptor, such as your jj config or your `PATH`. The
page also checks each time you open it.

- **Binary Source**: **Managed** uses a copy of jj that Sculptor downloads, and
  uses a `jj` on your `PATH` until you install that copy. **Custom** takes an
  absolute path or a command name, such as `/opt/homebrew/bin/jj`.
- **Install jj** downloads the managed copy. Sculptor never downloads jj until
  you click this. After that, at startup, it replaces a managed copy that is
  broken or no longer a supported version.
- **Minimum version**: Sculptor runs this jj release or any later 0.x release.
  The managed copy is this release.
- **Author identity**: the name and email jj records on your changes. If jj has
  none, the row shows a form, filled in from your git identity where it can be.
  **Save identity** writes them to your jj user config.
- **jj in your terminal**: shown when your shell profile puts a different jj
  first on `PATH`. Workspace terminals then run that jj, while agents run
  Sculptor's.

Sculptor can use jj only when it is installed, runs, is a supported version,
finds a git it accepts, and has an author identity, and when any other jj your
login shell runs is a supported version too. [When jj becomes
unavailable](#when-jj-becomes-unavailable) lists what to do about each.

---

## Turning on jj for a repository

Open **Settings > Repositories** and click **Configure** on the repository. The
**Jujutsu** group has two switches. While Sculptor can't use jj, both are
disabled, and the group says why, with an **Open Jujutsu settings** link and a
**Re-check** button.

### Is this repository a colocated jj repository?

A colocated repository has a `.jj` next to its `.git`, so git and jj both work
in it. jj workspaces need one. If you colocated the repository yourself, this
switch is already on whenever Sculptor can use jj.

Turning the switch on opens **Initialize jujutsu colocation**. Sculptor will run
`jj git init --colocate` in your repository, and first checks it:

- **These block it:** git submodules or Git LFS, which jj workspaces can't hold;
  a `.jj` that isn't colocated with the `.git`; and a git merge, rebase,
  cherry-pick or revert that stopped partway.
- **These get a warning:** git hooks, which won't run in jj workspaces, and a
  sparse checkout, which works differently there.
- **This gets a note:** your uncommitted changes become jj's working-copy
  commit.

Click **Initialize**. The switch shows **Initializing jujutsu colocation** while
jj runs, then turns on and locks. If jj fails, its error appears under the
switch with a **Retry** button.

Colocating leaves your own checkout working as before: your files, your branch
and `HEAD` stay as they are, and git keeps working. One thing changes:
afterwards `git status` shows untracked files as added, because jj records them.

Sculptor never removes a colocation, and never deletes your repository's `.jj`
directory. To undo a colocation, use the command line. A `.jj` that jj doesn't
read as colocated with the `.git` blocks colocation until you remove it
yourself.

### Use jj for new workspaces created in this repository

With this switch on, and Sculptor able to use jj, new workspaces in the
repository are jj workspaces, and the repository shows a **jj** badge in the
list. Sculptor turns it on when it
colocates the repository for you. For a repository you colocated yourself, turn
it on here. It stays disabled until the repository is colocated.

If you remove the colocation outside Sculptor, Sculptor turns this switch off.

---

## Creating a jj workspace

Create a workspace as usual. For a repository that uses jj, the form shows the
environment as **jj workspace**. Unless you have turned on Clone or In-place
workspaces under **Settings > Experimental**, that label is a link to the
repository's settings, which is where the choice is made.

- **Bookmark name (required)** is the bookmark the workspace will create. It is
  filled in from the same naming pattern as a branch name (**Settings > Git**,
  or the repository's own pattern).
- **source** is the bookmark to start from: a local one such as `main`, or a
  remote one such as `main@origin`. Until you pick one it reads **same as
  target**, and the workspace starts from its target.

The workspace's target starts as the repository's trunk bookmark, usually
`main@origin`. Its working copy starts as a new, empty revision on top of the
source.

The **+** next to a repository in the sidebar creates a jj workspace too.

From the command line, `sculpt workspace create --strategy jj` and
`sculpt run --strategy jj` do the same. There, `--branch-name` is the bookmark
name and `--branch` the source.

---

## Bookmarks and the top bar

In a jj workspace the top bar shows a pill naming the workspace's bookmark.

Sculptor creates the bookmark you asked for at the end of an agent's turn, on
the newest revision that has a description. It does this only while the
workspace has no bookmark, exactly one described revision is newest, and the
name is still free. Until the bookmark exists, the pill shows the name greyed
out. Sculptor never moves a bookmark: keeping it on the newest work is the
agent's job, and Claude agents are reminded when their bookmark falls behind.

The pill can also show:

- **+N**: the workspace has N other bookmarks.
- **↑N**: N described revisions sit above the bookmark.
- **conflict**: the working copy has a conflict.

Hover the pill for a card listing the bookmarks, the working copy's change id,
commit id and description, any flags (**empty**, **conflict**, **divergent**,
**stale**), and the target. Click the pill to copy the bookmark name, or the
working copy's change id when there is no bookmark. In the sidebar, the
workspace's **Workspace actions** menu and its right-click menu offer **Copy
bookmark** and **Copy change id**.

The target is a bookmark such as `main@origin`. Change it from the top bar,
choosing from the repository's local and remote bookmarks. With none set, the
top bar reads **No target bookmark**.

---

## Reviewing changes

The Files panel uses jj's terms in a jj workspace:

- **Revisions** takes the place of the **Commits** tab. It lists the revisions
  from where the workspace forked off its target up to the working copy, newest
  first. Each row shows the first line of the description, or **(no description
  set)**, then the change id, the line stats and file count, when it changed,
  and the commit id.
  Badges mark bookmarks and the states **working copy**, **empty**,
  **conflict** and **divergent**. Click a revision to list its files, and click a
  file to see its diff.
- **Working copy** takes the place of the **Uncommitted** scope in the Changes
  tab. It shows the working-copy revision's changes against its parent. **All**
  shows everything since the workspace forked off its target.
- **Discard changes** restores the file from the working copy's parent. The
  dialog notes that the discarded content stays recoverable from the jj
  operation log.
- **Commit** asks the agent to commit with jj. See [Prompts](#prompts).

---

## Pushing and pull requests

**Create PR** asks the agent to push the workspace's bookmark and open a pull
request from it into the branch its target tracks: `main` for `main@origin`. If
there is no bookmark yet, the agent is asked to create it first. Agents are told
never to push without your permission. Pull requests need a GitHub `origin`, as
in any workspace.

With no target bookmark, **Create PR** is disabled, and its tooltip asks you to
pick a target bookmark from the target selector.

Sculptor finds the pull request by the workspace's bookmarks and shows its status
in the top bar, as for a branch.

A push from a jj workspace reaches the remote at once. Your own git checkout
lags behind: the pushed bookmark shows up among its git branches only after you
next run a jj command in that checkout.

---

## Prompts

**Settings > Jujutsu** holds the prompts sent from jj workspaces:

- **jj commit prompt** is sent when you click **Commit**.
- **jj PR creation prompt** is sent when you click **Create PR**.
- **jj CI Babysitter pipeline prompt** and **jj CI Babysitter merge conflict
  prompt** are sent by the [CI Babysitter](ci_babysitter.md) for pull requests
  from jj workspaces.

Each starts out unset, and Sculptor sends the matching git prompt instead,
shown under **Uses the git prompt:**. Click **Use suggested wording** for an
editable jj prompt, or **Use the git prompt** to go back. Whichever prompt is
sent, Sculptor adds that this is a jj workspace with no git inside it, and names
the bookmark to set or push and, for a pull request, the branch to open it into.

Right-click the **Commit** or **Create PR** button in a jj workspace to change
its prompt. Once a jj prompt is set, the menu offers **Edit jj prompt...**,
which opens it on this page. Until then it offers **Edit prompt...**, which
edits the git prompt and links to **Set a jj commit prompt** or **Set a jj PR
creation prompt**.

**Repositories using jj** lists the repositories whose new workspaces are jj
workspaces, each with a **Configure** link.

---

## Stale working copies

A jj workspace's working copy goes stale when a jj operation somewhere else in
the repository rewrites its revision, for example `jj op restore` in your own
checkout. jj then stops recording changes to the workspace's files.

Sculptor shows a banner saying so, with an **Update working copy** button.
Sculptor never updates a stale working copy by itself, because updating over
edits jj hasn't recorded can leave a divergent change behind. Agents that hit a
stale working copy are told to run `jj workspace update-stale`, check the result,
and tell you what happened.

---

## Large new files

jj leaves a new file untracked when it is bigger than its size limit, so the
file is in no diff, commit or push. jj's own limit is 1 MiB, which leaves out
updated lockfiles, so Sculptor sets 10 MiB in jj workspaces. Agents are told to
mention such a file to you rather than change jj's configuration.

The Changes tab of a jj workspace lists such files in a banner, **jj left N new
files out**, in both the **Working copy** and **All** scopes. The banner gives
each file's path with jj's reason, says to raise the limit or delete the files,
and links to **Settings > Jujutsu**. It appears when Sculptor next recomputes
the workspace's diff, which is after an agent's turn. It appears nowhere else:
not in the Revisions tab, the file tree, or the diff view.

Change the limit under **Settings > Jujutsu > Maximum new file size**, from 1 to
1024 MiB. An existing jj workspace picks up the new value when Sculptor next
resumes it, for example after a restart.

---

## When jj becomes unavailable

A repository that uses jj creates no jj workspaces while Sculptor can't use jj,
and Sculptor does not fall back to a worktree. The create form says "This
repository creates jj workspaces, and jj is unavailable." with an **Open
Jujutsu settings** link.

Sculptor says why in the same words wherever it refuses: the repository's jj
switches, the colocation dialog, and an agent that can't start. **Settings >
Jujutsu** shows the same problem as its callout. The reasons, and what to do:

- **"jj is not installed: install it or set its path on the Jujutsu settings
  page".** Click **Install jj**, or switch **Binary Source** to **Custom** and
  give the path to your own jj.
- **"jj cannot run: …"**, with jj's error. Fix that error, then click
  **Re-check**.
- **"jj … at … is not supported: Sculptor needs jj 0.47.1 or a newer
  compatible version".** Install the managed copy, or point Sculptor at a newer
  jj.
- **"jj runs git … at … to fetch and push, but jj needs git 2.42.0 or newer:
  install a newer git first on PATH, or set jj's git.executable-path to one"**,
  or, with no git at all, **"jj finds no git to fetch and push with: install git
  2.42.0 or newer, or set jj's git.executable-path to one".** jj runs git to
  fetch and push: the `git.executable-path` in your jj config, or else the first
  `git` on `PATH`. Install a newer git there, or point `git.executable-path` at
  one.
- **"your login shell runs jj … at …, but Sculptor needs jj 0.47.1 or a newer
  compatible version, because the repository is shared with the jj you run
  yourself: upgrade or remove that jj, or stop your shell profile putting its
  directory first on PATH".** Your colocated repository is also read by the jj
  in your own terminal, so that jj must be a supported version too. Upgrade or
  uninstall it, or change your shell profile so it no longer comes first on
  `PATH`.
- **"jj has no author identity: set its user.name and user.email on the
  Jujutsu settings page".** Fill in **Author identity** and click **Save
  identity**.

Existing jj workspaces keep their files, but no agent starts in them, and the
setup command doesn't run, until jj is usable again. An agent that can't start
shows **jj Not Available** with the reason and a **Go to Settings** link. After
fixing the problem, click **Re-check** on **Settings > Jujutsu**.

---

## Setup command

A repository with no setup command of its own runs
`jj git fetch --remote origin 2>/dev/null || true` when a jj workspace is created,
in place of the `git fetch` a worktree runs. Set your own under **Settings >
Repositories**, as for any repository.

---

## Deleting a jj workspace

Deleting a jj workspace deletes its directory and tells jj to forget the
workspace. Its bookmarks follow **Branch and bookmark deletion when a workspace
is removed** under **Settings > Git**:

- **Never** keeps them.
- **Delete if safe** forgets the ones merged into the target, and the ones the
  remote already has at the same commit.
- **Always** forgets all of them.

Forgetting a bookmark removes it locally only: the branch on the remote stays,
and so do the workspace's revisions. A bookmark with the target's name, and
bookmarks on another workspace's work, are never touched.

---

## Adding a repository from inside a jj workspace

If you add a folder that is inside a jj workspace, Sculptor adds the colocated
repository that workspace belongs to. A jj workspace of a repository that isn't
colocated with git can't be added.
