import type { Editor as TipTapEditor } from "@tiptap/react";

export type PseudoSkillName = "clear" | "copy" | "btw";

export type ArgMode = "none" | "required";

export const PSEUDO_SKILLS: ReadonlyArray<{
  name: PseudoSkillName;
  description: string;
  argMode: ArgMode;
}> = [
  { name: "clear", description: "Clear conversation context", argMode: "none" },
  { name: "copy", description: "Copy the last response to clipboard", argMode: "none" },
  { name: "btw", description: "Ask a read-only side question", argMode: "required" },
];

const PSEUDO_SKILL_NAMES: ReadonlySet<string> = new Set(PSEUDO_SKILLS.map((s) => s.name));
const PSEUDO_SKILL_BY_NAME: ReadonlyMap<PseudoSkillName, { argMode: ArgMode }> = new Map(
  PSEUDO_SKILLS.map((s) => [s.name, { argMode: s.argMode }]),
);

export const isPseudoSkill = (name: string): name is PseudoSkillName => {
  return PSEUDO_SKILL_NAMES.has(name);
};

export type ParsedPseudoSkillCommand = { name: PseudoSkillName; args: string };

// Matches ProseMirror's internal text-node concatenation for a single paragraph.
// Returns the text content that *follows* the leading mention, preserving
// embedded whitespace but stripping one leading separator.
const collectTextAfterMention = (paragraph: {
  childCount: number;
  child: (index: number) => { type: { name: string }; text?: string };
}): string => {
  const parts: Array<string> = [];
  for (let i = 1; i < paragraph.childCount; i += 1) {
    const child = paragraph.child(i);
    if (child.type.name === "text" && typeof child.text === "string") {
      parts.push(child.text);
    } else if (child.type.name === "hardBreak") {
      parts.push("\n");
    }
  }
  return parts.join("").replace(/^\s+/, "");
};

export const parsePseudoSkillCommand = (editor: TipTapEditor, promptDraft: string): ParsedPseudoSkillCommand | null => {
  const doc = editor.state.doc;
  if (doc.childCount === 1) {
    const paragraph = doc.child(0);
    if (paragraph.childCount >= 1) {
      const firstChild = paragraph.child(0);
      if (firstChild.type.name === "mention" && firstChild.attrs.mentionSuggestionChar === "/") {
        const id = firstChild.attrs.id as string;
        const name = id.startsWith("/") ? id.slice(1) : id;
        if (isPseudoSkill(name)) {
          const entry = PSEUDO_SKILL_BY_NAME.get(name);
          const trailing = collectTextAfterMention(paragraph);
          if (entry?.argMode === "none") {
            // TipTap's `/`-menu autocomplete inserts a trailing space after a
            // mention; that's still a bare /clear or /copy. Only fall through
            // when there's real non-whitespace text after the mention so a
            // draft like "/clear the cache" goes to main as a regular message.
            if (trailing.length === 0) {
              return { name, args: "" };
            }
          } else {
            return { name, args: trailing };
          }
        }
      }
    }
  }

  const trimmed = promptDraft.trim();
  for (const skill of PSEUDO_SKILLS) {
    const slashName = `/${skill.name}`;
    if (skill.argMode === "none") {
      if (trimmed === slashName) {
        return { name: skill.name, args: "" };
      }
      continue;
    }

    if (trimmed === slashName) {
      return { name: skill.name, args: "" };
    }

    if (trimmed.startsWith(slashName)) {
      const rest = trimmed.slice(slashName.length);
      if (/^\s/.test(rest)) {
        return { name: skill.name, args: rest.replace(/^\s+/, "") };
      }
      // `/btwfoo` — prefix match but no whitespace delimiter. Not a command.
      return null;
    }
  }

  return null;
};
