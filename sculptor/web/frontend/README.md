# Sculptor frontend

## Quickstart

When running for the first time:

```
nvm install
npm install
```

Then:

```
nvm use
npm run dev
```

## Dynamically generated types.

The `src/generated-types.d.ts` file contains types generated dynamically from the pydantic annotations of the web endpoints.
They are regenerated every time you run vite build or vite serve (e.g. via `npm run dev`). If you need to run it manually, run:

```
npm run generate-types
```
