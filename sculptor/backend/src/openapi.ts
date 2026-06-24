import { writeFile } from "node:fs/promises";

import { buildApp } from "~/app";
import overlay from "~/openapi_overlay.json";

// Named-component + operationId overlay (Task 9.4, RW-API-4). fastify-type-
// provider-zod inlines route schemas, so @fastify/swagger emits no named
// `components/schemas` and auto-derives operation ids — but the generated
// clients (frontend openapi-ts + the sculpt python client) expect the SAME
// named types and operation ids the FastAPI document exposed. The overlay
// carries those exact wire shapes + the path→method→operationId map (snapshotted
// from the Python OpenAPI, the wire contract the rewrite reproduces); we merge
// them onto the emitted document so both clients regenerate compatibly. When the
// Python backend is deleted (Task 9.6) this snapshot stays as the canonical
// wire-type definition.
type OverlayDoc = {
  openapi?: string;
  info?: unknown;
  components?: { schemas?: Record<string, unknown> };
  paths?: Record<string, Record<string, unknown>>;
};

function applyOverlay(document: OverlayDoc): OverlayDoc {
  // The overlay's components + operations use OpenAPI 3.1 encoding (the FastAPI
  // snapshot's null/anyOf form). @fastify/swagger declares 3.0.3, where the same
  // shapes would be mis-read by the generators — so adopt 3.1.0 to match the
  // injected content.
  document.openapi = "3.1.0";
  // Match the FastAPI document's title/version so openapi-python-client derives
  // the same generated package name (sculptor_v1_api_client) the justfile expects.
  document.info = overlay.info;
  document.components ??= {};
  // Overlay names win for the shared types the clients import; any schema the
  // emit already named is preserved underneath.
  document.components.schemas = {
    ...(document.components.schemas ?? {}),
    ...overlay.schemas,
  };
  // For each HTTP operation present in BOTH the emitted doc and the snapshot,
  // adopt the snapshot operation (its responses/requestBody/parameters $ref the
  // named components), so the generated SDK's signatures match the components by
  // construction. WebSocket-only paths (no snapshot entry) keep their emitted
  // form; the TS Zod schemas still validate the real responses at runtime.
  for (const [path, methods] of Object.entries(overlay.operations)) {
    const emitted = document.paths?.[path];
    if (emitted === undefined) {
      continue;
    }
    for (const [method, operation] of Object.entries(methods)) {
      if (emitted[method] !== undefined) {
        emitted[method] = operation;
      }
    }
  }
  return document;
}

// Produces the OpenAPI document from the built app's Zod route schemas. Builds
// the app, waits for plugin registration (@fastify/swagger populates the spec
// during .ready()), then returns the generated document, with the named-
// component/operationId overlay applied. No server is started.
export async function generateOpenApiDocument(): Promise<object> {
  const app = buildApp();
  try {
    await app.ready();
    // @fastify/swagger augments the instance with .swagger() once registered.
    const document = (
      app as unknown as { swagger: () => OverlayDoc }
    ).swagger();
    return applyOverlay(document);
  } finally {
    await app.close();
  }
}

export async function emitOpenApiToFile(path: string): Promise<void> {
  const document = await generateOpenApiDocument();
  await writeFile(path, JSON.stringify(document, null, 2));
}
