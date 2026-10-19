const CATALOG_SCOPE_WARNING = "Saved-source research catalog only; it does not authorize execution or replay.";

export function warningsBeyondScopeNote(warnings: string[]): string[] {
  return warnings.filter(warning => warning !== CATALOG_SCOPE_WARNING);
}
