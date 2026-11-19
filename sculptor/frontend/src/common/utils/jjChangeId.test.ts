import { describe, expect, it } from "vitest";

import { shortChangeId } from "./jjChangeId.ts";

const CHANGE_ID = "kxqpmzvyrstuwlnokxqpmzvyrstuwlno";

describe("shortChangeId", () => {
  it("shows eight characters when a shorter prefix is unique", () => {
    expect(shortChangeId({ changeId: CHANGE_ID, uniquePrefixLength: 2 })).toEqual({
      uniquePrefix: "kx",
      rest: "qpmzvy",
    });
  });

  it("shows the whole unique prefix when it is longer than eight characters", () => {
    expect(shortChangeId({ changeId: CHANGE_ID, uniquePrefixLength: 10 })).toEqual({
      uniquePrefix: "kxqpmzvyrs",
      rest: "",
    });
  });
});
