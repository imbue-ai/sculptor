# pi Auth — Credentials & the Authenticated Catalog

How Sculptor and pi agree on which LLM providers are authenticated, where that
state lives, and how Sculptor reads/writes it.

> Source of truth: `sculptor/sculptor/agents/pi_agent/authenticated_providers.py`
> (path resolution, reading, presence model) and
> `sculptor/sculptor/services/pi_login_service.py` (driving pi's interactive
> `/login` and `/logout`). The deeper design rationale and the empirical phase-0
> feasibility findings are in `agent_docs/pi-auth/` — this page is the
> code-anchored quick reference.

## `~/.pi/agent/auth.json` is the shared source of truth

pi stores provider credentials in `auth.json` inside its agent directory.
Sculptor treats **the same file** as the source of truth, so Sculptor-managed pi
and standalone pi converge on one credential store.

`auth.json` is a flat object whose **top-level keys are provider ids** (e.g.
`{"anthropic": {"type": "api_key", "key": "..."}}`)
(`read_auth_json_provider_ids` at `authenticated_providers.py:40-57`).

### `getAgentDir` resolution

`resolve_pi_auth_json_path` (`authenticated_providers.py:26-37`) mirrors pi's own
`getAgentDir()`:

1. If the env var **`PI_CODING_AGENT_DIR`** is set and non-empty → use it
   (expanded).
2. Otherwise → `~/.pi/agent`.

`auth.json` lives directly inside that directory.

> When Sculptor drives pi's interactive `/login`/`/logout`, the PTY **inherits
> the user's real environment and explicitly does NOT set `PI_CODING_AGENT_DIR`**,
> so pi reads/writes the user's real `~/.pi/agent/auth.json`
> (`pi_login_service.py:245-247`). That is how the standalone-pi and
> Sculptor-pi views stay the same file.

## Catalog gating is on credential **presence**, not validity

A provider's models appear in pi's catalog if a credential **exists** for it —
even an empty or expired one. There is no validity check at gating time.

- `ProviderAuthStatus.in_auth_json` "reflects presence of the provider id as a
  top-level key in `auth.json` (presence, not validity, matching pi's gating)"
  (`authenticated_providers.py:10-16`).
- Test: a file containing `{"anthropic": {"key": ""}}` (empty/invalid key) still
  reports `{"anthropic"}` as authenticated
  (`authenticated_providers_test.py`, `test_reader_presence_not_validity`).
- Sculptor mirrors pi's behavior when curating the picker: `_curate_models` drops
  options whose provider is not in the authenticated set, precisely because "pi
  gates its catalog on credential presence, not validity, so a stray ambient key
  would otherwise leak that provider's models into the picker"
  (`agent_wrapper.py:333-337`, `350-351`).

**Consequence:** "this provider is in the catalog" means "a credential is
present," not "the credential works." A present-but-bogus key still surfaces the
provider's whole model set.

## Precedence: read carefully — two different layers

There are two distinct notions of precedence; do not conflate them.

1. **pi's own runtime credential resolution.** When a provider has both an
   `auth.json` entry and an environment variable, **pi prefers the `auth.json`
   entry** (auth.json > env). This is pi-core behavior, documented in the
   architecture write-up (`agent_docs/pi-auth/architecture.md`), not something
   Sculptor implements.
2. **Sculptor's authenticated-set computation (for catalog gating).** Sculptor
   does **not** apply precedence — it takes the **union**:
   `compute_authenticated_provider_ids()` returns
   `read_auth_json_provider_ids() | detect_env_authenticated_provider_ids()`
   (`authenticated_providers.py:71-73`). A provider counts as authenticated if it
   has a credential in **either** source.

So: Sculptor decides *whether to show* a provider by union (either source), and
pi decides *which credential value to actually use* by preferring `auth.json`.

## Writing credentials (`write_auth_json_entry`)

When Sculptor writes a key from Settings, it does a **merge-safe** read-modify-
write (`write_auth_json_entry` at `authenticated_providers.py:80-102`):

- Sets `data[provider_id] = {"type": "api_key", "key": <value>}`, preserving
  every other entry (including OAuth / unknown entries).
- The value is stored **verbatim** — a literal key, a `$ENV` reference, or a
  `!command` — so pi resolves it at read time and **no secret is resolved or
  logged** in Sculptor.
- Written atomically (temp file + rename) at mode **`0600`**
  (`_write_auth_json_atomically` at `authenticated_providers.py:105-116`).
- A garbled (non-dict / unparseable) existing file raises `PiAuthJsonError`
  rather than clobbering the user's credentials.

## `/logout` is per-provider

Logout removes **one** provider's stored key at a time — it is not an
all-providers reset.

`_drive_pi_session` (`pi_login_service.py:206-224`) submits `/logout`, waits for
pi's logout selector, then **fuzzy-filters pi's provider list to the chosen
`provider_id`** (typing the id narrows to its row) and presses Return to remove
that provider's stored key. The provider to remove is known up front (the user
clicked its Disconnect), and is passed as `spawn(mode, pi_binary_path,
provider_id)` (`pi_login_service.py:240-248`).

`/login` and `/logout` are both driven through an ephemeral PTY, never via
flags — Sculptor reaches pi's interactive surface, it does not reimplement it.
