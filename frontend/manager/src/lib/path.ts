// dotted-path read of a nested config object — mirrors backend _set_dotted's
// counterpart so the editor reads the same shape it writes back.
export function getPath(obj: unknown, path: string): unknown {
  if (obj == null) return undefined;
  let cur: unknown = obj;
  for (const seg of path.split(".")) {
    if (cur && typeof cur === "object" && seg in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[seg];
    } else {
      return undefined;
    }
  }
  return cur;
}
