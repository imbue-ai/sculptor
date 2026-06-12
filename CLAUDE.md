# Interaction Guidelines

- When the user asks a question, answer the question directly. Do not treat questions as requests for code changes or other work.
- When the task is ambiguous, pause and ask the user how to proceed before taking action.
- When the user expects you to check with them before proceeding, wait for their explicit confirmation. Do not continue with the task until they confirm.

# Transparency: Signing Off as Claude

When posting any message, comment, or content to services outside the local machine — including GitHub, GitLab, Slack, Linear, email, or any other external system — always sign off so it is transparent that the message was written by an agent rather than a person. End every such message with the following on its own final line:

```
(Sent by Claude)
```

This applies to MR/PR descriptions and comments, issue comments, Slack messages, Linear comments, and any other communication sent to a service outside this machine. It does NOT apply to code, commit messages (which use the existing `Co-authored-by` trailer), or local files.

# Public Visibility: Commit Messages and PR Descriptions

Treat every commit message and every MR/PR title and description as **permanently, world-readable**. This is a public repo, so write them for an outside reader who has no access to any private context, and never include anything private.

Before writing a commit message or an MR/PR description, scrub it of:

- **PII** — real people's full names, personal email addresses, individual usernames, and local filesystem paths that embed a username (e.g. `/Users/jdoe/...`). Use generic placeholders (`dev`, `<user>`, `/Users/<user>/...`) or refer to roles ("the reviewer", "the team") instead.
- **Internal-only references** — internal hostnames and URLs, internal service/tool/infra names, internal dashboards, and verbatim private discussion from tickets or chat. A bare Linear ticket ID (e.g. `SCU-1447`) as a reference is fine; pasting the private contents of that ticket is not.
- **Customer information** — customer names, customer-specific data, deployment details, or anything covered by an NDA.
- **Security-sensitive detail** — secrets, tokens, or credentials (never, anywhere), and exploit steps or descriptions of internal security mechanisms written in a way that would help an attacker. Describe security fixes at a safe altitude (e.g. "harden auth token validation") rather than as a reproduction recipe.
- **Candid internal commentary** — business strategy, unreleased plans, speculation about competitors, or remarks about individuals.

State the *why* of a change in terms that are both useful and safe to publish. When the real motivation is sensitive, summarize it at an altitude that is safe for a public reader rather than omitting context entirely.

This also applies to anything the `git-provider` skill or any workflow generates on your behalf (MR/PR bodies, squash-commit messages). The `/code-review-checklist` skill checks for these same issues.

# CRITICAL: Code Quality and Style

**IT IS CRITICAL TO FOLLOW ALL INSTRUCTIONS IN THIS FILE AND THE STYLE GUIDE DURING YOUR WORK.**

Before implementing any code changes:
1. Read `docs/development/style_guide.md`
2. Prioritize readability and simplicity - well-structured, maintainable code is the goal

All commands run from the repo root via [just](https://github.com/casey/just). See the [justfile](./justfile) at the root of the repo.

**When committing, run the following commands. Do NOT run them preemptively while iterating on changes — only when you are ready to commit:**

```
just format
just check
just test-unit
```

## Working with the repo and git

When asked to create or manage merge/pull requests, refer to the `git-provider` skill — it covers detecting the host from the `origin` remote and the matching CLI and commands to use.

If you create a new worktree, clone or copy of Sculptor, run `just rebuild` to install the proper dependencies.

## Formatting, Linting, and Type Checking

When fixing lint errors, be careful with some common gotchas:
- Use `# noqa: F811` for pytest fixture parameters that shadow imports (don't rename them)
- Use `# noqa: E731` for intentional lambda assignments (don't convert to functions)
- Use `# noqa: E402` for intentional late imports
- Use `# noqa: E712` for SQLAlchemy comparisons like `column == False`

## Frontend UI guidelines

- When placing `IconButton` components in a `Flex`, use `gap="2"` because Radix icon buttons apply negative margins on hover to display the hover background.

## Frontend type generation

TypeScript types are generated from backend models. When adding new `ElementIDs` for tests you will need to regenerate types.

Run the following command to generate types if they are missing, or you make updates:
```
just generate-api
```

## Testing

Before running tests directly, ALWAYS check for available skills. See the `justfile` to see the commands we use to run tests.

## Ratchets

Check the ratchets (these specific commands must be run from the root directory of the repository):
```
just ratchets
```

Figure out which ratchets are broken:
```
just ratchets-broken
```

## Git Safety Protocol

- NEVER run destructive/irreversible git commands (like `push --force`, hard reset) unless explicitly requested
- NEVER skip hooks (`--no-verify`, `--no-gpg-sign`) unless explicitly requested
- Write clear, descriptive commit messages that explain the "why" not just the "what"
- Keep commits atomic - one logical change per commit
- Run tests as part of committing, not preemptively during iteration
