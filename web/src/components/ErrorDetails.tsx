"use client";

import { useEffect } from "react";
import {
  failureCategory,
  failureReference,
  recordFailure,
  type FailureResource,
} from "@/lib/failures";

export default function ErrorDetails({
  error,
  resource,
}: {
  error: Error & { digest?: string };
  resource: Extract<FailureResource, "route" | "layout">;
}) {
  const reference = failureReference(error);
  useEffect(() => {
    recordFailure(resource, error);
  }, [resource, error]);
  return (
    <>
      <p className="error-detail">Failure category: {failureCategory(error)}</p>
      {reference && <p className="error-detail">Error reference: {reference}</p>}
    </>
  );
}
