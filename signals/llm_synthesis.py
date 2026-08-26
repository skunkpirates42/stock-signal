"""LLM synthesis layer.

Turns a rule-based signal into a human-readable reasoning blurb for journaling/alerts.
This is *presentation only* — it never changes the decision (per CLAUDE.md).

Provider is chosen by config.LLM_PROVIDER ('anthropic', 'groq', or 'template'). Any
provider failure (missing key, network, SDK error) falls back to a deterministic template
built from the votes, so the pipeline always produces reasoning and can run fully offline.
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


def _prompt_for(signal: dict) -> str:
    facts = json.dumps({k: signal.get(k) for k in
                        ("ticker", "direction", "confidence", "entry", "stop", "target",
                         "rr", "votes", "vote_tally")})
    if signal["direction"] == "WAIT":
        task = ("Explain in at most two sentences why this rule-based engine stood aside "
                "(WAIT) on this bar, referencing which indicator votes disagreed.")
    else:
        task = ("Explain in at most two sentences why this rule-based engine fired this "
                "signal, referencing the indicator votes that support it.")
    return (
        "You are summarizing a rule-based intraday trading signal for a personal trading "
        "journal. The decision has already been made by rules; you are not being asked to "
        "evaluate, agree with, or change it. Do not add price predictions or advice. "
        + task
        + " Reply with the explanation text only, no preamble and no JSON.\n\n"
        + "Signal: " + facts
    )


def _anthropic_reasoning(signal: dict):
    from anthropic import Anthropic

    # synthesize() runs inside the live bar handler (live/trader.py), which is invoked
    # synchronously from the asyncio websocket callback — a slow/hung request here stalls
    # bar aggregation and exit checks for every ticker, so fail fast instead of retrying.
    client = Anthropic(timeout=10.0, max_retries=0)
    resp = client.messages.create(
        model=config.LLM_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": _prompt_for(signal)}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise ValueError("empty response")
    return text, "anthropic:%s" % config.LLM_MODEL


def _groq_reasoning(signal: dict):
    from openai import OpenAI

    # See _anthropic_reasoning: this also runs inside the live bar handler and must not
    # stall the event loop, so keep the timeout short and skip retries.
    client = OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url=config.GROQ_BASE_URL,
        timeout=10.0,
        max_retries=0,
    )
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": _prompt_for(signal)}],
        # qwen3.6 is a reasoning model; without this it emits <think> scratchpad into content
        reasoning_effort="none",
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise ValueError("empty response")
    return text, "groq:%s" % config.GROQ_MODEL


def synthesize(signal: dict) -> dict:
    """Attach `reasoning` and `synthesis_source` to the signal.

    Presentation only — never changes the decision. Any provider failure degrades to the
    offline template so the trading loop cannot be blocked by an API outage.
    """
    provider = config.LLM_PROVIDER
    try:
        if provider == "anthropic":
            text, source = _anthropic_reasoning(signal)
        elif provider == "groq":
            text, source = _groq_reasoning(signal)
        else:
            text, source = _template_reasoning(signal), "template"
    except Exception as exc:
        text = _template_reasoning(signal)
        source = "template (fell back from %s: %s)" % (provider, exc)

    signal["reasoning"] = text
    signal["synthesis_source"] = source
    return signal
