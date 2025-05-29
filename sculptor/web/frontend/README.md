# Sculptor frontend

## Quickstart

When running the first time:

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

The `src/generated-types.d.ts` file contains types dynamically generated based on the pydantic annotation of the web endpoints inputs and outputs.
They are generated automatically when you run vite build or vite serve (e.g. via `npm run dev`). If you need to run it manually, run:

```
npm run generate-types
```
