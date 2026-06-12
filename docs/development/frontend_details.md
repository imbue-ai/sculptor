# Frontend Details

The frontend lives in `sculptor/frontend/`. See here for the [frontend style guide](./style/frontend.md).
Tech stack is listed below.

| Library        | Purpose                 |
|----------------|-------------------------|
| React          | UI framework            |
| TypeScript     | Type-safe JavaScript    |
| Jotai          | State management        |
| Radix UI       | Component library       |
| Vite           | Build tooling           |
| React Router   | Routing                 |
| SCSS Modules   | Component-scoped styles |
| Electron Forge | Desktop app packaging   |

The backend streams most UI-relevant state over a single WebSocket. Most components just read from global state via hooks — no fetching, no `useEffect` coordination.

UI state is derived on the backend (backend-for-frontend). TypeScript types are generated from backend models. The frontend consumes shaped UI data, not raw domain objects.

### WebSocket

Full snapshot on connect, then deltas. See `useUnifiedStream.ts`, `taskDetailReducers.ts`.

### Request Tracking

Interactive components (buttons, forms) stay consistent with WebSocket state:
- Every API call gets a `requestID`
- Backend includes it in the WebSocket update
- API client waits for the matching `requestID` before resolving

See `requestStore.ts`, `requestTracking.ts`, `apiClient.ts`.

### API Client

Generated via HeyAPI from FastAPI. Regenerate after endpoint changes:

```bash
just generate-api
```

Config in `openapi-ts.config.ts`.

### Styling

1. **Radix UI props** — `<Flex gap="2">`, `<Text size="2">`
2. **Design tokens** — `var(--space-4)`, `var(--accent-9)`
3. **SCSS Modules** — component-specific styles
4. **Inline styles** — only for runtime-computed values

Design tokens enforced by the `sculptor/no-hardcoded-values` stylelint rule (from the design-tokens plugin in `scripts/stylelint-plugin-design-tokens/`). Radix overrides in `src/styles/radix-overrides.css`.
