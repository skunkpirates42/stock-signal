"""LLM synthesis layer.

Turns a rule-based signal into a human-readable reasoning blurb for journaling/alerts.
This is *presentation only* — it never changes the decision (per CLAUDE.md).

If ANTHROPIC_API_KEY is set, it calls Claude for the reasoning. If not (the PoC default),
it falls back to a deterministic template built from the votes, so the pipeline runs fully
offline and reproducibly.
"""

import json
import os

import config


def _template_reasoning(signal: dict) -> str:
    """Deterministic, offline reasoning string assembled from the votes."""
    tally = signal["vote_tally"]
    votes = signal["votes"]
    direction = signal["direction"]

    if direction == "WAIT":
        return (
            f"{signal['ticker']}: indicators are split "
            f"({tally['bull']} bullish / {tally['bear']} bearish / {tally['neutral']} neutral) — "
            f"below the {round(config.CONFIDENCE_THRESHOLD * 100)}% agreement threshold or "
            f"insufficient reward:risk. Standing aside."
        )

    # Only the votes on the winning side actually support the chosen direction.
    side = "bull" if direction == "LONG" else "bear"
    supporting = [k for k, v in votes.items() if v == side]
    lean = "bullish" if direction == "LONG" else "bearish"
    return (
        f"{signal['ticker']} {direction} @ {signal['entry']} "
        f"(stop {signal['stop']}, target {signal['target']}, R:R {signal['rr']}). "
        f"{tally['bull']} bullish vs {tally['bear']} bearish votes give "
        f"{round(signal['confidence'] * 100)}% confidence. "
        f"Supporting signals: {', '.join(supporting)}. Net lean: {lean}."
    )


def synthesize(signal: dict) -> dict:
    """Attach a `reasoning` string to the signal.

    Returns the signal dict augmented with `reasoning` and `synthesis_source`
    ('llm' or 'template').
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        signal["reasoning"] = _template_reasoning(signal)
        signal["synthesis_source"] = "template"
        return signal

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        prompt = (
            "You are summarizing a rule-based intraday trading signal for a personal "
            "trading journal. Do NOT change the decision. Given this signal data, return "
            "ONLY a JSON object with a single key `reasoning` whose value is a concise "
            "(<=2 sentence) plain-English explanation referencing the indicator votes.\n\n"
            f"Signal: {json.dumps({k: signal[k] for k in ('ticker', 'direction', 'confidence', 'entry', 'stop', 'target', 'rr', 'votes', 'vote_tally')})}"
        )
        resp = client.messages.create(
            model=config.LLM_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        reasoning = json.loads(text).get("reasoning", text)
        signal["reasoning"] = reasoning
        signal["synthesis_source"] = "llm"
    except Exception as exc:  # network/parse/SDK errors -> graceful fallback
        signal["reasoning"] = _template_reasoning(signal)
        signal["synthesis_source"] = f"template (llm failed: {exc})"
    return signal
