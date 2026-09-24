import { isOpaqueDemoId } from "@/lib/demo";
import { proxyArtifact } from "@/lib/artifact-proxy";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ resultId: string; artifactId: string }> }) {
  const { resultId, artifactId } = await params;
  if (!isOpaqueDemoId(resultId) || !isOpaqueDemoId(artifactId)) {
    return new Response(null, { status: 404, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } });
  }
  return proxyArtifact(`/results/${resultId}/artifacts/${artifactId}`);
}
