/** A Linear ticket reference, parsed from a branch name or typed by the user. */
export type Ticket = {
  /** Team key, upper-cased (e.g. "SCU"). */
  key: string;
  /** Issue number within the team. */
  number: number;
  /** Canonical "<KEY>-<NUMBER>" identifier (e.g. "SCU-1495"). */
  identifier: string;
};

/**
 * Pull a Linear ticket out of a string. Sculptor branches follow
 * `<user>/<ticket-id>-<title>` (e.g. `dev/scu-1495-example`), so the first
 * `<letters>-<digits>` run is the ticket; the same parse also accepts a raw id
 * a user types in (e.g. "SCU-1495"). Returns `null` when nothing matches.
 *
 * This is only a *fallback* for the primary ticket: Linear's
 * `issueVcsBranchSearch` is the authoritative branch→issue link (see
 * `linear/client.ts`); this regex covers branches Linear hasn't linked yet.
 */
export const parseTicket = (input: string | null): Ticket | null => {
  if (!input) return null;
  const match = input.match(/([a-zA-Z]{2,})-(\d+)/);
  if (!match) return null;
  const key = match[1].toUpperCase();
  const number = Number(match[2]);
  return { key, number, identifier: `${key}-${number}` };
};
