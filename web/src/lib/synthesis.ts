const PROVIDER_FALLBACK = /^template \(fell back from ([^:]+):/;

export function hasLlmReasoning(synthesisSource: string | null): boolean {
  if (!synthesisSource) return false;
  return !synthesisSource.startsWith("template");
}

export function describeSynthesisSource(synthesisSource: string | null): string {
  if (!synthesisSource) return "provenance not recorded";
  const failedProvider = PROVIDER_FALLBACK.exec(synthesisSource)?.[1];
  return failedProvider ? `template (${failedProvider} explanation failed)` : synthesisSource;
}
