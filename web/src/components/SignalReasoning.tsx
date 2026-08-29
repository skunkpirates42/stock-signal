"use client";

import { useState, useTransition } from "react";
import { explainSignal } from "@/lib/actions";
import { hasLlmReasoning } from "@/lib/synthesis";

export interface SignalReasoningProps {
  signalId: number;
  reasoning: string | null;
  synthesisSource: string | null;
}

export default function SignalReasoning({
  signalId,
  reasoning,
  synthesisSource,
}: SignalReasoningProps) {
  const [text, setText] = useState(reasoning);
  const [source, setSource] = useState(synthesisSource);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const explained = hasLlmReasoning(source);

  function handleExplain() {
    setError(null);
    startTransition(async () => {
      try {
        const result = await explainSignal(signalId);
        setText(result.reasoning);
        setSource(result.synthesis_source);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "explain failed");
      }
    });
  }

  return (
    <div className="rationale-reasoning">
      <p>{text ?? "No reasoning recorded for this signal."}</p>
      <p className="rationale-provenance">
        Source: {source ?? "provenance not recorded"}
      </p>
      {!explained && (
        <button
          type="button"
          className="button button-inline"
          onClick={handleExplain}
          disabled={isPending}
        >
          {isPending ? "Explaining…" : "Explain with AI"}
        </button>
      )}
      {error && <p className="rationale-explain-error">Could not explain: {error}</p>}
    </div>
  );
}
