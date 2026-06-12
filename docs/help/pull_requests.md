# Pull Requests

Once you've committed changes on a workspace branch, click **Create PR** in the
top bar. Sculptor pushes the branch and opens a pull request on GitHub against
your target branch.

Sculptor uses the GitHub CLI (`gh`) under the hood. The first time, you may need
to run `gh auth login` in a terminal.

---

## Tracking status

After the pull request exists, the button shows its status inline and refreshes
on its own:

- Whether it's **open**, **merged**, or **closed**
- Review approvals and unresolved comments
- CI / checks status

Open the button's menu to view details or edit the prompt Sculptor uses to create
the PR.

---

GitLab is also supported (via the `glab` CLI).
