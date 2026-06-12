# Desktop App

Sculptor is packaged as a desktop app using [Electron Forge](https://www.electronforge.io/).

## Commands

```bash
just refresh    # Build prerequisite assets (required first)
just app        # Package as .app and create .dmg installer
just pkg        # Package only (no installer)
```

Skip notarization for local testing:

```bash
SKIP_NOTARIZE_AND_SIGN=1 just app
```

Start with a built-in backend (instead of connecting to an existing one):

```bash
just refresh
START_BACKEND_IN_DEV=1 just start
```

## Passing Arguments to Backend

Prefix backend arguments with `--sculptor=`:

```bash
./frontend/out/sculptor-darwin-arm64/sculptor.app/Contents/MacOS/sculptor --sculptor=--foo --sculptor=--bar
```

With `npm run electron:start`, use two `--` separators:

```bash
cd frontend
npm run electron:start -- -- --sculptor='--foo --bar'
```

## Multiple Instances

Multiple instances are prevented by default (shared database race conditions). For testing, use separate data directories:

```bash
env SCULPTOR_USER_DATA_DIR=$HOME/sculptor-data-1 SCULPTOR_FOLDER=$HOME/sculptor-1 open -n Sculptor.app
```
