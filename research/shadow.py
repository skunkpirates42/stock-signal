"""Offline-only baseline/RVOL shadow portfolios.

The runner consumes caller-supplied completed bars.  It neither imports a data source nor
creates a broker/LLM client: both variants use isolated ``PaperBroker`` instances.
"""
from __future__ import annotations

from collections import deque
import copy
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
import uuid

import pandas as pd

import config
from data.sessions import calendar, flatten_due, in_regular_hours, session_bounds, utc
from signals.engine import generate_signal
from signals.indicators import compute_indicators
from signals.quality import POLICY
from trades.executor import FillPolicy, PaperBroker
from trades.tracker import check_exit

VARIANTS = ("baseline", "rvol")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def _bar(value):
    needed = ("timestamp", "open", "high", "low", "close", "volume")
    if any(key not in value for key in needed):
        raise ValueError("completed bar requires OHLCV")
    ts = utc(value["timestamp"])
    if not in_regular_hours(ts):
        raise ValueError("shadow accepts regular-hours completed bars only")
    opening, closing = session_bounds(ts)
    if ((ts - opening) % pd.Timedelta(minutes=POLICY["bar_minutes"]) != pd.Timedelta(0)
            or ts + pd.Timedelta(minutes=POLICY["bar_minutes"]) > closing):
        raise ValueError("bar is not an exchange-aligned completed bucket")
    result = {"timestamp": ts.isoformat()}
    for key in needed[1:]:
        result[key] = float(value[key])
    if (not all(math.isfinite(v) for key, v in result.items() if key != "timestamp")
            or result["volume"] < 0 or min(result["open"], result["high"], result["low"], result["close"]) <= 0
            or result["high"] < max(result["open"], result["low"], result["close"])
            or result["low"] > min(result["open"], result["high"], result["close"])):
        raise ValueError("invalid completed bar")
    return result


def _day(ts):
    return str(utc(ts).tz_convert("America/New_York").date())


def _registration(value):
    required = ("operator", "prospective_start", "review_after_completed_sessions")
    if not isinstance(value, dict) or any(not value.get(key) for key in required):
        raise ValueError("registration requires operator, prospective_start, and review_after_completed_sessions")
    start = utc(value["prospective_start"])
    if pd.isna(start) or int(value["review_after_completed_sessions"]) < 1:
        raise ValueError("invalid registration")
    return {**value, "prospective_start": start.isoformat(),
            "review_after_completed_sessions": int(value["review_after_completed_sessions"])}


def _code_identity():
    """Hash every local module that can affect a shadow decision or simulated fill."""
    root = Path(__file__).resolve().parents[1]
    paths = (Path(__file__), root / "data" / "sessions.py", root / "signals" / "quality.py",
             root / "signals" / "engine.py", root / "signals" / "indicators.py",
             root / "trades" / "executor.py", root / "trades" / "tracker.py")
    digest = sha256()
    for path in paths:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return {"decision_and_fill_sha256": digest.hexdigest(), "quality_policy_version": POLICY["version"]}


class ShadowRunner:
    """Persist immutable events, explicit completed-session history and local state."""
    def __init__(self, symbols, *, db_path, feed_identity, registration, run_id=None,
                 window_size=120, max_event_lag_minutes=10, candidate_factory=None,
                 candidate_factory_identity=None):
        if not symbols or not feed_identity:
            raise ValueError("symbols and feed_identity are required")
        self.symbols = tuple(sorted(set(symbols)))
        self.db_path, self.feed_identity = str(db_path), str(feed_identity)
        self.registration = _registration(registration)
        self.window_size = int(window_size)
        self.max_lag = pd.Timedelta(minutes=max_event_lag_minutes)
        self.candidate_factory = candidate_factory
        if candidate_factory is not None and not candidate_factory_identity:
            raise ValueError("candidate_factory requires an immutable candidate_factory_identity")
        self.candidate_factory_identity = candidate_factory_identity
        self._init()
        with self._connect() as conn:
            if run_id is None:
                run_id = uuid.uuid4().hex
                manifest = self._manifest()
                conn.execute("INSERT INTO shadow_runs VALUES (?,?,?,?)", (run_id, _json(manifest), self.feed_identity, pd.Timestamp.now(tz="UTC").isoformat()))
            row = conn.execute("SELECT manifest_json,feed_identity FROM shadow_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or row["feed_identity"] != self.feed_identity:
                raise ValueError("unknown shadow run or feed identity mismatch")
            if json.loads(row["manifest_json"]) != self._manifest():
                raise ValueError("frozen shadow code, configuration, feed, or registration differs from existing run")
            self.run_id = run_id
            state = conn.execute("SELECT state_json FROM shadow_state WHERE run_id=?", (run_id,)).fetchone()
            value = json.loads(state["state_json"]) if state else {}
            self.windows = {s: deque(value.get("windows", {}).get(s, []), maxlen=self.window_size) for s in self.symbols}
            self.watermark = utc(value["watermark"]) if value.get("watermark") else None
            self.current_day = value.get("current_day")
            self.variants = {}
            for variant in VARIANTS:
                raw = value.get("variants", {}).get(variant, {})
                broker = PaperBroker(policy=FillPolicy.configured())
                broker.account = f"shadow:{run_id}:{variant}"
                broker.capital = raw.get("capital", broker.capital)
                broker.open_positions = raw.get("open_positions", {})
                broker.closed_trades = raw.get("closed_trades", [])
                self.variants[variant] = {"broker": broker, "pending": raw.get("pending", {}), "count": raw.get("count", {s: 0 for s in self.symbols})}

    def _manifest(self):
        settings = {k: v for k, v in vars(config).items() if k.isupper() and isinstance(v, (str, int, float))
                    and not any(x in k for x in ("KEY", "SECRET", "PATH", "BROKER", "PROVIDER"))}
        return {"source": "shadow", "backend": "local", "feed_identity": self.feed_identity,
                "symbols": list(self.symbols), "policy": POLICY, "registration": self.registration,
                "window_size": self.window_size, "max_event_lag_minutes": self.max_lag.total_seconds() / 60,
                "candidate_factory_identity": self.candidate_factory_identity,
                "code_identity": _code_identity(),
                "config_identity": sha256(_json(settings).encode()).hexdigest(), "settings": settings,
                "data_identity": {"feed": self.feed_identity}, "fill_policy": "next_completed_5min_close"}

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS shadow_runs(run_id TEXT PRIMARY KEY,manifest_json TEXT NOT NULL,feed_identity TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS shadow_events(run_id TEXT,timestamp TEXT,feed_identity TEXT,event_sha256 TEXT,received_at TEXT,payload_json TEXT,PRIMARY KEY(run_id,timestamp));
            CREATE TABLE IF NOT EXISTS shadow_history(run_id TEXT,symbol TEXT,timestamp TEXT,payload_json TEXT,PRIMARY KEY(run_id,symbol,timestamp));
            CREATE TABLE IF NOT EXISTS shadow_sessions(run_id TEXT,session_day TEXT,completed_at TEXT,PRIMARY KEY(run_id,session_day));
            CREATE TABLE IF NOT EXISTS shadow_seeded_sessions(run_id TEXT,session_day TEXT,completed_at TEXT,PRIMARY KEY(run_id,session_day));
            CREATE TABLE IF NOT EXISTS shadow_history_initializations(run_id TEXT PRIMARY KEY,initialized_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS shadow_state(run_id TEXT PRIMARY KEY,state_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS shadow_candidates(run_id TEXT,variant TEXT,timestamp TEXT,symbol TEXT,raw_json TEXT,eligibility_json TEXT,gate_json TEXT,status TEXT,PRIMARY KEY(run_id,variant,timestamp,symbol));
            CREATE TABLE IF NOT EXISTS shadow_positions(run_id TEXT,variant TEXT,timestamp TEXT,symbol TEXT,event_kind TEXT,payload_json TEXT,PRIMARY KEY(run_id,variant,timestamp,symbol,event_kind));
            CREATE TABLE IF NOT EXISTS shadow_marks(run_id TEXT,variant TEXT,timestamp TEXT,payload_json TEXT,PRIMARY KEY(run_id,variant,timestamp));
            CREATE TABLE IF NOT EXISTS shadow_issues(run_id TEXT,timestamp TEXT,reason TEXT,payload_json TEXT,PRIMARY KEY(run_id,timestamp,reason));
            """)

    def initialize_history(self, bars_by_symbol, *, completed_sessions, feed_identity=None):
        if feed_identity is not None and str(feed_identity) != self.feed_identity:
            raise ValueError("history feed identity mismatch")
        if self.watermark is not None:
            raise ValueError("history initialization is locked after completed-event capture begins")
        complete = {str(day) for day in completed_sessions}
        start = utc(self.registration["prospective_start"])
        if set(bars_by_symbol) != set(self.symbols):
            raise ValueError("history must cover every tracked symbol")
        expected = {}
        for day in complete:
            bounds = session_bounds(day + "T17:00Z")
            if bounds is None:
                raise ValueError("history session is invalid or not completed before prospective_start")
            opening, closing = bounds
            if closing > start:
                raise ValueError("history session is invalid or not completed before prospective_start")
            expected[day] = {value.isoformat() for value in pd.date_range(
                opening, closing - pd.Timedelta(minutes=POLICY["bar_minutes"]),
                freq=f'{POLICY["bar_minutes"]}min')}
        snapshot = self._snapshot()
        try:
            with self._connect() as conn:
                if (conn.execute("SELECT 1 FROM shadow_history_initializations WHERE run_id=?", (self.run_id,)).fetchone()
                        or conn.execute("SELECT 1 FROM shadow_history WHERE run_id=? LIMIT 1", (self.run_id,)).fetchone()):
                    raise ValueError("history initialization is one-time and cannot append older sessions")
                for symbol, bars in bars_by_symbol.items():
                    if symbol not in self.symbols:
                        raise ValueError("untracked history symbol")
                    normalized, previous = [], None
                    for raw in bars:
                        bar = _bar(raw)
                        timestamp = utc(bar["timestamp"])
                        if timestamp >= start or _day(timestamp) not in complete:
                            raise ValueError("history contains a future or undeclared session bar")
                        if previous is not None and timestamp <= previous:
                            raise ValueError("history bars must be unique and strictly chronological")
                        normalized.append(bar)
                        previous = timestamp
                    for day, timestamps in expected.items():
                        actual = {bar["timestamp"] for bar in normalized if _day(bar["timestamp"]) == day}
                        if actual != timestamps:
                            raise ValueError("history session is incomplete")
                    for bar in normalized:
                        old = conn.execute("SELECT payload_json FROM shadow_history WHERE run_id=? AND symbol=? AND timestamp=?", (self.run_id,symbol,bar["timestamp"])).fetchone()
                        if old and old["payload_json"] != _json(bar):
                            raise ValueError("conflicting historical bar")
                        if not old:
                            conn.execute("INSERT INTO shadow_history VALUES (?,?,?,?)", (self.run_id,symbol,bar["timestamp"],_json(bar)))
                            self.windows[symbol].append(bar)
                for day in complete:
                    conn.execute("INSERT INTO shadow_seeded_sessions VALUES (?,?,?)", (self.run_id,day,day+"T23:59:59+00:00"))
                conn.execute("INSERT INTO shadow_history_initializations VALUES (?,?)",
                             (self.run_id, pd.Timestamp.now(tz="UTC").isoformat()))
                self._save(conn)
        except Exception:
            self._restore(snapshot)
            raise

    def _history(self, conn, symbol, timestamp):
        row = conn.execute("SELECT payload_json FROM shadow_history WHERE run_id=? AND symbol=? AND timestamp=?", (self.run_id,symbol,utc(timestamp).isoformat())).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def _complete_session(self, conn, day, completed_at):
        """Mark a session only when every expected completed bucket was captured."""
        bounds = session_bounds(day + "T17:00Z")
        if bounds is None:
            return
        opening, closing = bounds
        expected = {value.isoformat() for value in pd.date_range(
            opening, closing - pd.Timedelta(minutes=POLICY["bar_minutes"]),
            freq=f'{POLICY["bar_minutes"]}min')}
        complete = True
        for symbol in self.symbols:
            rows = conn.execute("SELECT timestamp FROM shadow_history WHERE run_id=? AND symbol=? AND timestamp>=? AND timestamp<?",
                                (self.run_id, symbol, opening.isoformat(), closing.isoformat())).fetchall()
            if {row["timestamp"] for row in rows} != expected:
                complete = False
                break
        if complete:
            conn.execute("INSERT OR IGNORE INTO shadow_sessions VALUES (?,?,?)", (self.run_id, day, utc(completed_at).isoformat()))
        else:
            conn.execute("INSERT OR IGNORE INTO shadow_issues VALUES (?,?,?,?)",
                         (self.run_id, utc(completed_at).isoformat(), "incomplete_session",
                          _json({"session_day": day, "feed_identity": self.feed_identity})))

    def _snapshot(self):
        return copy.deepcopy((self.windows, self.watermark, self.current_day, self.variants))

    def _restore(self, snapshot):
        self.windows, self.watermark, self.current_day, self.variants = snapshot

    def _rvol(self, conn, symbol, ts):
        pair, day = session_bounds(ts), _day(ts)
        detail = {"value": None, "threshold": POLICY["rvol_threshold"], "accepted": False, "observations": 0, "reason": "missing_current_bar"}
        current = self._history(conn, symbol, ts)
        if pair is None or current is None: return detail
        offset, values = utc(ts)-pair[0], []
        prior_days = [str(x.date()) for x in calendar(int(day[:4])).sessions if str(x.date()) < day][-POLICY["rvol_prior_sessions"]:]
        for prior in prior_days:
            if not (conn.execute("SELECT 1 FROM shadow_sessions WHERE run_id=? AND session_day=?", (self.run_id,prior)).fetchone()
                    or conn.execute("SELECT 1 FROM shadow_seeded_sessions WHERE run_id=? AND session_day=?", (self.run_id,prior)).fetchone()):
                continue
            opening, closing = session_bounds(prior+"T17:00Z"); bucket = opening+offset
            row = self._history(conn,symbol,bucket)
            if bucket+pd.Timedelta(minutes=5) <= closing and row is not None and row["volume"] >= 0: values.append(row["volume"])
        detail["observations"] = len(values)
        if len(values) < POLICY["rvol_min_observations"]: return {**detail,"reason":"insufficient_prior_sessions"}
        median = float(pd.Series(values).median())
        if median <= 0: return {**detail,"reason":"zero_reference_volume"}
        value = current["volume"] / median; accepted = value >= POLICY["rvol_threshold"]
        return {**detail,"value":value,"reference_median":median,"accepted":accepted,"reason":"passed" if accepted else "below_threshold"}

    def _candidate(self, symbol):
        if len(self.windows[symbol]) < config.WARMUP_BARS: return None
        if self.candidate_factory:
            value = self.candidate_factory(symbol, tuple(json.loads(_json(x)) for x in self.windows[symbol]))
            if not isinstance(value,dict): raise ValueError("candidate_factory must return a dict")
            return json.loads(_json(value))
        return generate_signal(symbol, compute_indicators(pd.DataFrame(self.windows[symbol])))

    def process_completed_batch(self, bars, *, received_at=None, feed_identity=None):
        if feed_identity is not None and str(feed_identity) != self.feed_identity: raise ValueError("event feed identity mismatch")
        if set(bars) != set(self.symbols):
            return {"processed":False,"reason":"missing_or_extra_symbols"}
        payload = {s:_bar(bars[s]) for s in self.symbols}; times = {x["timestamp"] for x in payload.values()}
        if len(times) != 1: raise ValueError("batch timestamps differ")
        ts = utc(times.pop()); encoded = _json(payload); digest = sha256(encoded.encode()).hexdigest(); received = utc(received_at or ts+pd.Timedelta(minutes=5))
        if ts < utc(self.registration["prospective_start"]):
            raise ValueError("completed event precedes registered prospective_start")
        if received < ts + pd.Timedelta(minutes=POLICY["bar_minutes"]):
            raise ValueError("bar is not yet completed at received_at")
        snapshot = self._snapshot()
        try:
            with self._connect() as conn:
                prior = conn.execute("SELECT event_sha256 FROM shadow_events WHERE run_id=? AND timestamp=?", (self.run_id,ts.isoformat())).fetchone()
                if prior:
                    if prior["event_sha256"] != digest: raise ValueError("conflicting duplicate completed batch")
                    return {"processed":False,"duplicate":True,"event_sha256":digest}
                if self.watermark is not None and ts <= self.watermark: raise ValueError("out-of-order completed batch")
                day = _day(ts)
                if self.current_day and day != self.current_day: self._complete_session(conn, self.current_day, ts)
                conn.execute("INSERT INTO shadow_events VALUES (?,?,?,?,?,?)", (self.run_id,ts.isoformat(),self.feed_identity,digest,received.isoformat(),encoded))
                for s,bar in payload.items():
                    conn.execute("INSERT INTO shadow_history VALUES (?,?,?,?)", (self.run_id,s,bar["timestamp"],_json(bar))); self.windows[s].append(bar)
                    for state in self.variants.values(): state["count"][s] = state["count"].get(s,0)+1
                self.watermark,self.current_day = ts,day; stale = received-(ts+pd.Timedelta(minutes=5)) > self.max_lag
                for variant,state in self.variants.items(): self._run_variant(conn,variant,state,payload,ts,stale)
                # Record the current prospective session as soon as its final bucket
                # is captured.  Its date remains excluded from its own RVOL decision.
                if ts + pd.Timedelta(minutes=POLICY["bar_minutes"]) == session_bounds(ts)[1]:
                    self._complete_session(conn, day, received)
                self._save(conn)
        except Exception:
            self._restore(snapshot)
            raise
        return {"processed":True,"event_sha256":digest,"stale":stale}

    def _run_variant(self, conn, variant, state, bars, ts, stale):
        broker, decision = state["broker"], ts+pd.Timedelta(minutes=5); executable = decision < session_bounds(ts)[1]; exited = set()
        # Match ``LiveTrader``: existing positions are observed (and may exit) before
        # a queued candidate can enter on this bar.  A new position cannot see this
        # bar's range as an exit trigger.
        for s,bar in bars.items():
            pos = broker.open_positions.get(s)
            if not pos: continue
            pos["observed_bars"] = pos.get("observed_bars",0)+1
            flatten = config.SESSION_POLICY == "flatten" and flatten_due(decision)
            if not stale and executable and (pos.get("pending_exit") or flatten):
                reason = pos.get("pending_exit", {}).get("reason", "session_close")
                outcome = pos.get("pending_exit", {}).get("outcome", "session_close")
                trade=broker.close_position(s,bar["close"],outcome,state["count"][s],bars_held=pos["observed_bars"],exit_reason=reason,exit_at=decision.isoformat()); exited.add(s)
                conn.execute("INSERT OR REPLACE INTO shadow_positions VALUES (?,?,?,?,?,?)",(self.run_id,variant,ts.isoformat(),s,"close",_json(trade)))
            elif not stale and check_exit(pos,bar):
                pos["pending_exit"] = check_exit(pos,bar)
        # A candidate is executable only on the next fresh completed observation in
        # its own session and within the local replay's ten-minute decision window.
        for s,bar in bars.items():
            pending = state["pending"].pop(s,None)
            if not pending:
                continue
            same_session = utc(pending["decision_at"]).date() == ts.date()
            timely = pd.Timedelta(0) < decision - utc(pending["decision_at"]) <= pd.Timedelta(minutes=10)
            closing = session_bounds(ts)[1]
            session_closing = config.SESSION_POLICY == "flatten" and decision >= closing - pd.Timedelta(minutes=5)
            if (not stale and executable and same_session and timely and not session_closing
                    and not broker.has_open(s) and s not in exited):
                pos = broker.open_position({**pending,"entry":bar["close"],"entry_at":decision.isoformat()},state["count"][s])
                if pos: conn.execute("INSERT OR REPLACE INTO shadow_positions VALUES (?,?,?,?,?,?)",(self.run_id,variant,ts.isoformat(),s,"open",_json(pos)))
        for s in self.symbols:
            raw=self._candidate(s)
            if raw is None: continue
            raw={**raw,"ticker":s,"decision_at":decision.isoformat()}
            rvol=self._rvol(conn,s,ts); gate={"mode":variant,"policy":POLICY,"accepted":variant=="baseline" or rvol["accepted"],"reason":"passed" if variant=="baseline" else rvol["reason"],"checks":{} if variant=="baseline" else {"rvol":rvol}}
            reason=raw.get("skip_reason") or ("wait" if raw.get("direction")=="WAIT" else None)
            if stale: reason="stale_data"
            elif not executable: reason="session_closed"
            elif broker.has_open(s): reason="position_open"
            elif s in exited: reason="exited_this_bar"
            elif config.SESSION_POLICY == "flatten" and decision >= session_bounds(ts)[1] - pd.Timedelta(minutes=10): reason="session_closing"
            elif not gate["accepted"] and not reason: reason="quality_gate"
            eligible={"eligible":reason is None,"reason":reason,"feed_identity":self.feed_identity,"portfolio_account":broker.account,"decision_at":decision.isoformat()}
            conn.execute("INSERT INTO shadow_candidates VALUES (?,?,?,?,?,?,?,?)",(self.run_id,variant,ts.isoformat(),s,_json(raw),_json(eligible),_json(gate),"queued" if reason is None else "rejected"))
            if reason is None: state["pending"][s]=raw
        unrealized=sum((1 if p["direction"]=="LONG" else -1)*(bars[s]["close"]-p["entry"])*p["shares"]-p.get("entry_cost",0)-broker.policy.cost(bars[s]["close"],p["shares"]) for s,p in broker.open_positions.items())
        mark={"capital":broker.capital,"marked_equity":round(broker.capital+unrealized,2),"costs":round(sum(t.get("costs",0) for t in broker.closed_trades),2),"open_positions":len(broker.open_positions)}
        conn.execute("INSERT OR REPLACE INTO shadow_marks VALUES (?,?,?,?)",(self.run_id,variant,ts.isoformat(),_json(mark)))

    def _save(self, conn):
        variants={name:{"capital":x["broker"].capital,"open_positions":x["broker"].open_positions,"closed_trades":x["broker"].closed_trades,"pending":x["pending"],"count":x["count"]} for name,x in self.variants.items()}
        conn.execute("INSERT OR REPLACE INTO shadow_state VALUES (?,?)",(self.run_id,_json({"windows":{s:list(w) for s,w in self.windows.items()},"watermark":self.watermark.isoformat() if self.watermark is not None else None,"current_day":self.current_day,"variants":variants})))

    def artifact(self):
        with self._connect() as conn:
            return {"run_id":self.run_id,"events":conn.execute("SELECT count(*) FROM shadow_events WHERE run_id=?",(self.run_id,)).fetchone()[0],"completed_sessions":conn.execute("SELECT count(*) FROM shadow_sessions WHERE run_id=?",(self.run_id,)).fetchone()[0],"seeded_history_sessions":conn.execute("SELECT count(*) FROM shadow_seeded_sessions WHERE run_id=?",(self.run_id,)).fetchone()[0],"variants":{v:{"account":x["broker"].account,"capital":x["broker"].capital,"candidates":conn.execute("SELECT count(*) FROM shadow_candidates WHERE run_id=? AND variant=?",(self.run_id,v)).fetchone()[0]} for v,x in self.variants.items()}}


def replay_shadow(events, *, symbols, db_path, feed_identity, registration, history=None, completed_sessions=(), **kwargs):
    """Offline replay entry point; deliberately ignores ``config.BROKER``."""
    runner=ShadowRunner(symbols,db_path=db_path,feed_identity=feed_identity,registration=registration,**kwargs)
    if history: runner.initialize_history(history,completed_sessions=completed_sessions,feed_identity=feed_identity)
    for event in events:
        # Replay envelopes preserve the original receipt time.  Bare mappings remain
        # supported for existing offline fixtures, where receipt is the bar close.
        if isinstance(event, dict) and "bars" in event:
            batch, received_at = event["bars"], event.get("received_at")
        else:
            batch, received_at = event, None
        runner.process_completed_batch(batch, received_at=received_at, feed_identity=feed_identity)
    return runner.artifact()
