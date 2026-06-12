# CLI Tools

## sculpt (Sculptor API CLI)

Command-line interface for the Sculptor API, located in `tools/sculpt/`.

### Updating the Skill

After changing CLI commands, update `sculptor/sculptor-plugin/skills/sculpt-cli/SKILL.md` to reflect current commands.

### Regenerating the API Client

The CLI uses a generated Python client built from the Sculptor OpenAPI spec. It is generated into `tools/sculpt/sculpt/client/` (gitignored, not checked in):

```bash
just generate-sculpt-client
```

### Running Tests

```bash
cd tools/sculpt

uv run pytest              # all tests
uv run pytest tests/unit/  # unit tests only
uv run pytest tests/test_e2e.py  # end-to-end
```

HTTP interactions in the unit tests are mocked with `respx`.
