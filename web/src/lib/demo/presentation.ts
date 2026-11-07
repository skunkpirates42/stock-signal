import type { Availability } from "@/lib/demo/contracts";

export function artifactHref(resultId: string, artifactId: string) {
  return `/api/demo/v1/results/${encodeURIComponent(resultId)}/artifacts/${encodeURIComponent(artifactId)}`;
}

export function availabilityText(value: Availability<string>): string {
  return value.availability === "available" ? value.value : `Unavailable: ${value.detail}`;
}
