"""Tests for AlpacaBroker using an injected fake client (no network)."""

import pytest

from trades.alpaca_broker import AlpacaBroker


class FakeOrder:
    def __init__(self, id, status="filled", filled_avg_price=None, filled_qty=None):
        self.id = id
        self.status = status
        self.filled_avg_price = filled_avg_price
        self.filled_qty = filled_qty


class FakeAccount:
    def __init__(self, equity):
        self.equity = str(equity)


class FakePosition:
    def __init__(self, symbol):
        self.symbol = symbol


class FakeClient:
    """Fills every order immediately at the configured price/qty."""

    def __init__(self, equity=100_000.0, entry_fill=100.5, exit_fill=104.0,
                 submit_status="accepted", poll_status="filled", positions=()):
        self.equity = equity
        self.entry_fill = entry_fill
        self.exit_fill = exit_fill
        self.submit_status = submit_status
        self.poll_status = poll_status
        self.submitted = []
        self._orders = {}
        self._n = 0
        self.positions = list(positions)

    def get_account(self):
        return FakeAccount(self.equity)

    def submit_order(self, order_data=None):
        self._n += 1
        oid = f"o{self._n}"
        self.submitted.append(order_data)
        self._orders[oid] = FakeOrder(oid, self.poll_status, str(self.entry_fill),
                                      str(order_data.qty))
        return FakeOrder(oid, self.submit_status)

    def close_position(self, symbol):
        self._n += 1
        oid = f"c{self._n}"
        self._orders[oid] = FakeOrder(oid, "filled", str(self.exit_fill), "1")
        return FakeOrder(oid, "accepted")

    def get_order_by_id(self, oid):
        return self._orders[oid]

    def get_all_positions(self):
        return self.positions


def _broker(client):
    return AlpacaBroker(client=client, fill_timeout=0.0, poll_interval=0)


LONG = {"ticker": "NVDA", "direction": "LONG", "entry": 100.0, "stop": 98.0, "target": 104.0}
SHORT = {"ticker": "TSLA", "direction": "SHORT", "entry": 100.0, "stop": 102.0, "target": 94.0}


def test_open_uses_real_fill_not_signal_entry():
    b = _broker(FakeClient(equity=100_000, entry_fill=100.5))
    pos = b.open_position(LONG, entry_bar=5, signal_id=1)
    assert pos["entry"] == 100.5             # real fill, not the 100.0 bar-close plan
    assert pos["shares"] == 100              # 10% of 100k / 100.0
    assert pos["stop"] == 98.0 and pos["target"] == 104.0  # planned levels stay absolute
    assert b.has_open("NVDA")


def test_open_short_submits_sell_side():
    from alpaca.trading.enums import OrderSide

    client = FakeClient()
    b = _broker(client)
    b.open_position(SHORT, entry_bar=0)
    assert client.submitted[-1].side == OrderSide.SELL


def test_close_long_uses_real_exit_fill_and_pnl():
    b = _broker(FakeClient(entry_fill=100.5, exit_fill=104.0))
    b.open_position(LONG, entry_bar=1)
    trade = b.close_position("NVDA", exit_price=104.0, outcome="WIN", exit_bar=7)
    assert trade["exit_price"] == 104.0
    assert trade["pnl"] == pytest.approx((104.0 - 100.5) * 100)
    assert trade["outcome"] == "WIN"          # our logic decides WIN/LOSS, not Alpaca
    assert trade["bars_held"] == 6
    assert not b.has_open("NVDA")


def test_close_short_pnl_direction():
    b = _broker(FakeClient(entry_fill=100.0, exit_fill=98.0))
    b.open_position(SHORT, entry_bar=0)
    trade = b.close_position("TSLA", exit_price=98.0, outcome="WIN", exit_bar=3)
    # short profits when price falls: (entry - exit) * shares
    assert trade["pnl"] == pytest.approx((100.0 - 98.0) * trade["shares"])


def test_no_second_position_same_ticker():
    b = _broker(FakeClient())
    assert b.open_position(LONG, entry_bar=0) is not None
    assert b.open_position(LONG, entry_bar=1) is None


def test_position_too_small_returns_none():
    b = _broker(FakeClient(equity=5.0))   # 10% of $5 can't afford a $100 share
    assert b.open_position(LONG, entry_bar=0) is None


def test_wait_signal_never_opens():
    b = _broker(FakeClient())
    assert b.open_position({**LONG, "direction": "WAIT"}, entry_bar=0) is None


def test_await_fill_times_out_when_never_filled():
    b = _broker(FakeClient(poll_status="accepted"))   # order stays unfilled
    with pytest.raises(TimeoutError):
        b.open_position(LONG, entry_bar=0)


def test_await_fill_raises_on_reject():
    b = _broker(FakeClient(poll_status="rejected"))
    with pytest.raises(RuntimeError):
        b.open_position(LONG, entry_bar=0)


def test_close_falls_back_to_theoretical_on_error():
    client = FakeClient()
    b = _broker(client)
    b.open_position(LONG, entry_bar=0)
    client.close_position = lambda symbol: (_ for _ in ()).throw(RuntimeError("api down"))
    trade = b.close_position("NVDA", exit_price=104.0, outcome="WIN", exit_bar=2)
    assert trade["exit_price"] == 104.0   # fell back to the passed theoretical level
    assert trade["status"] == "CLOSED"


def test_alpaca_open_symbols_reconciliation():
    b = _broker(FakeClient(positions=[FakePosition("AAPL"), FakePosition("MSFT")]))
    assert b.alpaca_open_symbols() == {"AAPL", "MSFT"}
