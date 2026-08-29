export function hasLlmReasoning(synthesisSource: string | null): boolean {
  if (!synthesisSource) return false;
  return !synthesisSource.startsWith("template");
}
