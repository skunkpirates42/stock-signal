"""Provider dispatch for signal reasoning.

Nothing here touches the network: the anthropic/groq helpers are monkeypatched. The
contract under test is that synthesize() always produces a non-empty reasoning string
and an accurate synthesis_source, whatever the provider does.
"""

import openai

import config
from signals import llm_synthesis
from signals.llm_synthesis import synthesize


def _actionable():
    return {
        "ticker": "NVDA", "direction": "LONG", "confidence": 0.7167,
        "entry": 212.5, "stop": 211.6693, "target": 214.1615, "rr": 2.0,
        "votes": {"rsi": "neutral", "price_vs_sma20": "bull", "sma20_vs_sma50": "bull",
                  "price_vs_vwap": "bull", "macd": "bull", "bb": "neutral"},
        "vote_tally": {"bull": 4, "bear": 0, "neutral": 2},
    }


def _wait():
    return {
        "ticker": "AAPL", "direction": "WAIT", "confidence": 0.55,
        "entry": 327.6, "stop": None, "target": None, "rr": None,
        "votes": {"rsi": "neutral", "price_vs_sma20": "bull", "sma20_vs_sma50": "bull",
                  "price_vs_vwap": "bull", "macd": "bear", "bb": "neutral"},
        "vote_tally": {"bull": 3, "bear": 1, "neutral": 2},
    }


def test_template_provider_needs_no_network(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "template")
    out = synthesize(_actionable())
    assert out["synthesis_source"] == "template"
    assert "NVDA" in out["reasoning"]


def test_template_handles_wait_signals(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "template")
    out = synthesize(_wait())
    assert out["synthesis_source"] == "template"
    assert "Standing aside" in out["reasoning"]


def test_anthropic_provider_records_provider_and_model(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_synthesis, "_anthropic_reasoning",
                        lambda s: ("four of six lean bullish", "anthropic:claude-haiku-4-5"))
    out = synthesize(_actionable())
    assert out["reasoning"] == "four of six lean bullish"
    assert out["synthesis_source"] == "anthropic:claude-haiku-4-5"


def test_groq_provider_records_provider_and_model(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_synthesis, "_groq_reasoning",
                        lambda s: ("bullish lean", "groq:qwen/qwen3.6-27b"))
    out = synthesize(_actionable())
    assert out["synthesis_source"] == "groq:qwen/qwen3.6-27b"


def test_provider_failure_falls_back_to_template(monkeypatch):
    def boom(signal):
        raise RuntimeError("api down")

    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_synthesis, "_anthropic_reasoning", boom)
    out = synthesize(_actionable())
    assert "NVDA" in out["reasoning"]
    assert out["synthesis_source"].startswith("template")
    assert "api down" in out["synthesis_source"]


def test_unknown_provider_uses_template(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "nonesuch")
    out = synthesize(_actionable())
    assert out["synthesis_source"] == "template"


def test_groq_reasoning_disables_thinking_output(monkeypatch):
    captured = {}

    class FakeMessage:
        content = "four bullish votes support the call"

    class FakeResponse:
        choices = [type("Choice", (), {"message": FakeMessage()})()]

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", FakeClient)

    text, source = llm_synthesis._groq_reasoning(_actionable())

    assert captured["reasoning_effort"] == "none"
    assert text == "four bullish votes support the call"
    assert source == "groq:%s" % config.GROQ_MODEL


def test_prompt_forbids_changing_the_decision():
    prompt = llm_synthesis._prompt_for(_actionable())
    assert "NVDA" in prompt
    assert "LONG" in prompt
    assert "not" in prompt.lower()


def test_wait_prompt_asks_why_it_stood_aside():
    prompt = llm_synthesis._prompt_for(_wait())
    assert "WAIT" in prompt or "stood aside" in prompt.lower()
