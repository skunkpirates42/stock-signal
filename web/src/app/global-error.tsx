"use client";

import Page from "@/components/Page";
import ScopeNote from "@/components/ScopeNote";
import { fontVariableClasses } from "@/styles/fonts";
import "./globals.css";
import Button from "@/components/Button";

export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <html lang="en" className={fontVariableClasses}>
      <body>
        <title>Something went wrong</title>
        <div className="canvas">
          <Page>
            <h1>Something went wrong</h1>
            <ScopeNote>
              The dashboard failed to load. Try again, and if it keeps failing check the dashboard
              logs.
            </ScopeNote>
            <Button onClick={() => retry()}>Try again</Button>
            <p className="error-detail">{error.message}</p>
            {error.digest && <p className="error-detail">Error reference: {error.digest}</p>}
          </Page>
        </div>
      </body>
    </html>
  );
}
