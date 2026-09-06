"""XNYS session boundaries, including holidays, DST and early closes."""
from functools import lru_cache
import pandas as pd
import exchange_calendars as xcals


def utc(ts):
    ts = pd.Timestamp(ts)
    return ts.tz_localize('UTC') if ts.tzinfo is None else ts.tz_convert('UTC')


@lru_cache(maxsize=32)
def calendar(year):
    return xcals.get_calendar('XNYS', start=f'{year-1}-01-01', end=f'{year+1}-12-31')


@lru_cache(maxsize=4096)
def bounds(day):
    cal = calendar(int(day[:4]))
    if not cal.is_session(day):
        return None
    return utc(cal.session_open(day)), utc(cal.session_close(day))


def session_bounds(ts):
    return bounds(str(utc(ts).tz_convert('America/New_York').date()))


def in_regular_hours(ts):
    pair = session_bounds(ts)
    return bool(pair and pair[0] <= utc(ts) < pair[1])


def flatten_due(ts):
    pair = session_bounds(ts)
    return bool(pair and pair[1] - pd.Timedelta(minutes=5) <= utc(ts) < pair[1])
