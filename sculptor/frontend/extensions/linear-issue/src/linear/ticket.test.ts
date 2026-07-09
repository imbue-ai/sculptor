import { describe, expect, it } from "vitest";

import { parseTicket } from "./ticket.ts";

describe("parseTicket", () => {
  it("pulls the ticket out of a Sculptor branch name", () => {
    expect(parseTicket("user/scu-1495-example")).toEqual({ key: "SCU", number: 1495, identifier: "SCU-1495" });
  });

  it("accepts a raw identifier and upper-cases the team key", () => {
    expect(parseTicket("SCU-1552")).toEqual({ key: "SCU", number: 1552, identifier: "SCU-1552" });
    expect(parseTicket("abc-7")).toEqual({ key: "ABC", number: 7, identifier: "ABC-7" });
  });

  it("takes the first ticket when several appear", () => {
    expect(parseTicket("user/scu-1-and-abc-2")?.identifier).toBe("SCU-1");
  });

  it("requires a team key of at least two letters", () => {
    expect(parseTicket("x-9")).toBeNull();
  });

  it("returns null when there is no ticket (or no input)", () => {
    expect(parseTicket("main")).toBeNull();
    expect(parseTicket("")).toBeNull();
    expect(parseTicket(null)).toBeNull();
  });
});
