// Golden tests for the message_conversion fold (Task 4.2).
//
// Every fixture under __fixtures__/ was captured by running the REAL Python
// `convert_agent_messages_to_task_update` (see the task's golden-generator
// script) over inputs built the same way `message_conversion_test.py` builds
// them, then serializing the resulting ChatMessage[] to JSON. The TS fold must
// reproduce that JSON byte-for-byte (modulo key ordering, handled by deep
// equality). A second property test asserts that applying messages one at a
// time (the incremental warm-cache path) equals a full re-fold.

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { ChatMessage } from "~/projection/chat_types";
import {
  applyMessage,
  createFoldState,
  foldMessages,
  foldStateToChatMessages,
} from "~/projection/message_conversion";

interface Fixture {
  name: string;
  input: Record<string, unknown>[];
  expected: ChatMessage[];
}

const fixturesDir = join(dirname(fileURLToPath(import.meta.url)), "__fixtures__");

function loadFixtures(): Fixture[] {
  return readdirSync(fixturesDir)
    .filter((file) => file.endsWith(".json"))
    .sort()
    .map((file) => JSON.parse(readFileSync(join(fixturesDir, file), "utf8")) as Fixture);
}

const fixtures = loadFixtures();

describe("foldMessages golden fixtures", () => {
  it("loads at least the expected set of fixtures", () => {
    expect(fixtures.length).toBeGreaterThanOrEqual(20);
  });

  for (const fixture of fixtures) {
    it(`full fold reproduces Python output: ${fixture.name}`, () => {
      expect(foldMessages(fixture.input)).toEqual(fixture.expected);
    });

    it(`incremental fold equals full fold: ${fixture.name}`, () => {
      const state = createFoldState();
      for (const message of fixture.input) {
        applyMessage(state, message);
      }
      expect(foldStateToChatMessages(state)).toEqual(foldMessages(fixture.input));
    });

    it(`incremental fold reproduces Python output: ${fixture.name}`, () => {
      const state = createFoldState();
      for (const message of fixture.input) {
        applyMessage(state, message);
      }
      expect(foldStateToChatMessages(state)).toEqual(fixture.expected);
    });
  }
});
