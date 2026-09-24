import { isOpaqueDemoId } from "@/lib/demo";
import { proxyArtifact } from "@/lib/artifact-proxy";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ runId: string; artifactId: string }> }) {
  const { runId, artifactId } = await params;
  if (!isOpaqueDemoId(runId) || !isOpaqueDemoId(artifactId)) {
    return new Response(null, { status: 404, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } });
  }
  return proxyArtifact(`/runs/${runId}/artifacts/${artifactId}`);
}
