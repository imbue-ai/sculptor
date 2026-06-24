import { defineConfig } from "drizzle-kit";

// Generates SQLite DDL from the Drizzle schema into ./drizzle. The migration
// runner (Task 2.3) applies these to the database at startup.
export default defineConfig({
  dialect: "sqlite",
  schema: "./src/db/schema/index.ts",
  out: "./drizzle",
});
