import { writeFile } from "node:fs/promises";

import { buildApp } from "~/app";

// Produces the OpenAPI document from the built app's Zod route schemas. Builds
// the app, waits for plugin registration (@fastify/swagger populates the spec
// during .ready()), then returns the generated document. No server is started.
export async function generateOpenApiDocument(): Promise<object> {
  const app = buildApp();
  try {
    await app.ready();
    // @fastify/swagger augments the instance with .swagger() once registered.
    return (app as unknown as { swagger: () => object }).swagger();
  } finally {
    await app.close();
  }
}

export async function emitOpenApiToFile(path: string): Promise<void> {
  const document = await generateOpenApiDocument();
  await writeFile(path, JSON.stringify(document, null, 2));
}
