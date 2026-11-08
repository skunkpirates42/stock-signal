"use client";

import ErrorDetails from "@/components/ErrorDetails";
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
        This dashboard view could not be loaded. Try again. If the problem continues, use the error
        reference when checking the dashboard logs.
      </ScopeNote>
      <Button onClick={() => retry()}>Try again</Button>
      <ErrorDetails error={error} resource="route" />
    </Page>
  );
}
