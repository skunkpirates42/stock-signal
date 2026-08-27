"use client";

export default function Error({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <main className="canvas">
      <h1>Something went wrong</h1>
      <p className="error-message">
        This dashboard could not reach its data API. The most likely cause is that the Flask
        server on port 8000 is not running — start it and try again.
      </p>
      <p className="error-detail">{error.message}</p>
      <p className="error-actions">
        <button type="button" className="button" onClick={() => retry()}>
          Try again
        </button>
      </p>
    </main>
  );
}
