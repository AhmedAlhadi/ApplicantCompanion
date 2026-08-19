const UUID_PATTERN =
  "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";

function collectIds(chunk: string, into: string[]) {
  const found = chunk.match(new RegExp(UUID_PATTERN, "g")) ?? [];
  for (const id of found) {
    if (!into.includes(id)) into.push(id);
  }
}

/** Remove leaked evidence ids from employer-facing prose and recover them for remarks. */
export function stripInlineEvidence(text: string | undefined | null): { text: string; ids: string[] } {
  if (!text) return { text: "", ids: [] };
  const ids: string[] = [];
  const strip = (pattern: RegExp, value: string) =>
    value.replace(pattern, (match) => {
      collectIds(match, ids);
      return "";
    });
  let cleaned = strip(
    new RegExp(
      `\\s*[(\\[]\\s*(?:evidence(?:\\s*ids?)?|source(?:s)?|refs?|citations?)\\s*:?\\s*[0-9a-fA-F,\\s-]+[)\\]]\\.?`,
      "gi",
    ),
    text,
  );
  cleaned = strip(
    new RegExp(`(?:[,;.]?\\s*)(?:evidence(?:\\s*ids?)?)\\s*:\\s*[0-9a-fA-F,\\s-]+\\.?`, "gi"),
    cleaned,
  );
  cleaned = strip(
    new RegExp(
      `\\s*[(\\[]\\s*${UUID_PATTERN}(?:\\s*,\\s*${UUID_PATTERN})*\\s*[)\\]]\\.?`,
      "gi",
    ),
    cleaned,
  );
  cleaned = cleaned.replace(/[ \t]{2,}/g, " ").replace(/ +([,.;:])/g, "$1").trim();
  return { text: cleaned, ids };
}

export function mergeEvidenceIds(...groups: Array<string[] | undefined | null>): string[] {
  const out: string[] = [];
  for (const group of groups) {
    for (const id of group ?? []) {
      if (id && !out.includes(id)) out.push(id);
    }
  }
  return out;
}
