"""Central configuration for the paper-trading signal PoC.

Everything tunable lives here so the engine, data adapter, and logger stay free of
magic numbers. Values mirror the spec in CLAUDE.md.
"""

import os

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

# --- Paper execution / backtest --------------------------------------------
STARTING_CAPITAL = 100_000.0
WARMUP_BARS = 50              # need >= SMA_SLOW bars before generating signals
BACKTEST_BARS = 300          # synthetic bars to replay per ticker

# --- Storage ---------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "papertrader.db")

# --- Dashboard -------------------------------------------------------------
# Default 8000 (macOS uses port 5000 for AirPlay, so avoid it). Override with env.
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", 8000))

# --- Alerts ----------------------------------------------------------------
# Desktop (macOS) notifications fire from run_live.py's event hook. The browser
# UI has its own client-side filters; this only gates the native notifications.
ALERT_MIN_CONFIDENCE = 0.0    # min signal confidence to fire a desktop notification (0 = all actionable)
ALERT_SOUND = "Ping"          # macOS notification sound name ("" to silence)

# --- LLM -------------------------------------------------------------------
LLM_MODEL = "claude-sonnet-4-20250514"
