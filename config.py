"""Central configuration for the paper-trading signal PoC.

Everything tunable lives here so the engine, data adapter, and logger stay free of
magic numbers. Values mirror the spec in CLAUDE.md.
"""

import os
import math
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=False)

# --- Watchlist -------------------------------------------------------------
# SPY and QQQ double as market-regime context for filtering individual names later.
WATCHLIST = ["AAPL", "NVDA", "TSLA", "SPY", "QQQ", "MSFT", "AMZN", "META"]

# --- Signal thresholds -----------------------------------------------------
CONFIDENCE_THRESHOLD = 0.62   # >= this share of directional votes -> LONG/SHORT, else WAIT
MIN_RR = 2.0                  # reject trades whose reward:risk is below this

# --- Indicator parameters --------------------------------------------------
RSI_LENGTH = 14
SMA_FAST = 20
SMA_SLOW = 50
BB_LENGTH = 20
BB_STD = 2.0
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ATR_LENGTH = 14
VOLUME_AVG_LENGTH = 20        # rolling window for the volume ratio baseline

# RSI vote bands (from CLAUDE.md table)
RSI_BULL = 45                 # below -> bullish (strong below 30)
RSI_BEAR = 55                 # above -> bearish (strong above 70)

# Bollinger Band "near a band" cutoffs, expressed as %B position (0=lower, 1=upper)
BB_NEAR_LOWER = 0.20          # %B below this -> near lower band -> bullish
BB_NEAR_UPPER = 0.80          # %B above this -> near upper band -> bearish

# Volume ratio confirmation thresholds (modifier, not a directional vote)
VOLUME_CONFIRM = 1.2          # ratio above this confirms / boosts confidence
VOLUME_WEAKEN = 0.8           # ratio below this weakens / dampens confidence
VOLUME_CONFIDENCE_DELTA = 0.05  # how much the modifier nudges confidence

# --- Risk / sizing (entry/stop/target) -------------------------------------
ATR_STOP_MULT = 1.5
ATR_TARGET_MULT = 3.0
POSITION_PCT = 0.10           # 10% of capital per trade

# --- Broker backend --------------------------------------------------------
# 'local'  = in-memory PaperBroker (default; offline, no orders leave the machine).
# 'alpaca' = submit real market orders to the Alpaca paper account (requires
#            ALPACA_API_KEY / ALPACA_SECRET_KEY). Live loop only — the backtest always
#            uses the local broker since you can't submit orders against historical bars.
BROKER = os.environ.get("BROKER", "local").lower()
# How long to wait for a market order to fill before giving up (seconds).
ORDER_FILL_TIMEOUT = 10.0
ORDER_POLL_INTERVAL = 0.5

# --- Paper execution / backtest --------------------------------------------
STARTING_CAPITAL = 100_000.0
WARMUP_BARS = 50              # need >= SMA_SLOW bars before generating signals
BACKTEST_BARS = int(os.environ.get("BACKTEST_BARS", 300))   # bars to replay per ticker
# Trailing window fed to the indicators each bar. Bounded (not the full history) so the
# backtest is O(n) and uses the same lookback the live loop keeps in memory.
BACKTEST_LOOKBACK = 120

# --- Storage ---------------------------------------------------------------
# Live and replay storage have independent environment overrides.
DB_PATH = os.environ.get("DB_PATH") or os.path.join(os.path.dirname(__file__), "papertrader.db")

# --- Dashboard -------------------------------------------------------------
# Default 8000 (macOS uses port 5000 for AirPlay, so avoid it). Override with env.
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", 8000))

# --- Alerts ----------------------------------------------------------------
# Desktop (macOS) notifications fire from run_live.py's event hook. The browser
# UI has its own client-side filters; this only gates the native notifications.
ALERT_MIN_CONFIDENCE = 0.0    # min signal confidence to fire a desktop notification (0 = all actionable)
ALERT_SOUND = "Ping"          # macOS notification sound name ("" to silence)

# --- LLM -------------------------------------------------------------------
# Synthesis is presentation-only and never affects the trading decision, so any
# provider (or none) is safe. 'template' needs no network and no key.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-haiku-4-5")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Execution policies. Spread is round-trip basis points; slippage applies per fill.
ACCOUNT_NAMESPACE = os.environ.get("ACCOUNT_NAMESPACE", "local")
SESSION_POLICY = os.environ.get("SESSION_POLICY", "overnight")
SPREAD_BPS = float(os.environ.get("SPREAD_BPS", "0"))
SLIPPAGE_BPS = float(os.environ.get("SLIPPAGE_BPS", "0"))
FEE_PER_SHARE = float(os.environ.get("FEE_PER_SHARE", "0"))
BAR_LATENESS_SECONDS = float(os.environ.get("BAR_LATENESS_SECONDS", "35"))
BACKTEST_DB_PATH = os.environ.get("BACKTEST_DB_PATH") or os.path.join(os.path.dirname(__file__), "backtest.db")
if BROKER not in {"local", "alpaca"}:
    raise ValueError("BROKER must be local or alpaca")
if LLM_PROVIDER not in {"template", "groq", "anthropic"}:
    raise ValueError("LLM_PROVIDER must be template, groq, or anthropic")
if SESSION_POLICY not in {"overnight", "flatten"}:
    raise ValueError("SESSION_POLICY must be overnight or flatten")
if BACKTEST_BARS < WARMUP_BARS or not 0 < DASHBOARD_PORT < 65536:
    raise ValueError("Invalid BACKTEST_BARS or DASHBOARD_PORT")
if any(not math.isfinite(v) or v < 0 for v in (SPREAD_BPS, SLIPPAGE_BPS, FEE_PER_SHARE, BAR_LATENESS_SECONDS)):
    raise ValueError("Execution costs and lateness must be nonnegative")

def validate_live():
    if not (os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY")):
        raise ValueError("Live data requires ALPACA_API_KEY and ALPACA_SECRET_KEY")
