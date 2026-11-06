"use client";

import Page from "@/components/Page";
import ScopeNote from "@/components/ScopeNote";
import Button from "@/components/Button";

export default function Error({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <Page>
      <h1>Something went wrong</h1>
      <ScopeNote>
        This dashboard could not reach its data API. Check that the Flask API is running, and that
        FLASK_API_URL points at it if it is not on the default address, then try again.
      </ScopeNote>
      <Button onClick={() => retry()}>Try again</Button>
      <p className="error-detail">{error.message}</p>
      {error.digest && <p className="error-detail">Error reference: {error.digest}</p>}
    </Page>
  );
}
