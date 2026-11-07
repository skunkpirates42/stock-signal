import sqlite3

import pytest

from dashboard.app import create_app


@pytest.fixture
def journal(tmp_path):
    path = str(tmp_path / "signals.db")
    client = create_app(db_path=path).test_client()
    return path, client


def add_signal(
    connection,
    *,
    ticker="AAA",
    direction="LONG",
    confidence=0.75,
    timestamp="2026-06-10T12:00:00Z",
    created_at="2026-06-11T12:00:00Z",
    source="live",
    backend="local",
    account="paper",
):
    return connection.execute(
        """INSERT INTO signals
        (ticker, direction, confidence, bar_timestamp, created_at, source, backend, account)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, direction, confidence, timestamp, created_at, source, backend, account),
    ).lastrowid


def search(client, query=""):
    response = client.get("/api/signals/search" + ("?" + query if query else ""))
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    return response.get_json()


def test_searches_complete_journal_beyond_500_rows_with_bounded_stable_pages(journal):
    path, client = journal
    with sqlite3.connect(path) as connection:
        oldest = add_signal(connection, ticker="OLD", direction="SHORT", confidence=0.95)
        for _ in range(550):
            add_signal(connection)
    first = search(client, "page_size=100")
    assert first["total"] == first["scope_total"] == 551
    assert len(first["items"]) == 100
    assert first["total_pages"] == 6
    assert first["tickers"] == ["AAA", "OLD"]
    with sqlite3.connect(path) as connection:
        add_signal(connection, ticker="NEW")
    ids = [row["id"] for row in first["items"]]
    for page in range(2, 7):
        result = search(client, f"page_size=100&page={page}&snapshot_id={first['snapshot_id']}")
        assert result["total"] == 551
        ids.extend(row["id"] for row in result["items"])
    assert ids == list(range(551, 0, -1))
    assert search(client)["total"] == 552
    filtered = search(client, "ticker=old&direction=SHORT&min_confidence=0.95")
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == oldest
    assert search(client, "ticker=OLD&min_confidence=0.96")["total"] == 0


def test_page_boundaries_clamp_and_empty_results(journal):
    path, client = journal
    with sqlite3.connect(path) as connection:
        for _ in range(100):
            add_signal(connection)
    first = search(client)
    second = search(client, "page=2")
    assert (len(first["items"]), len(second["items"]), second["total_pages"]) == (50, 50, 2)
    assert first["items"][-1]["id"] == 51
    assert second["items"][0]["id"] == 50
    assert search(client, "page=999")["page"] == 2
    empty = search(client, "ticker=NONE&page=999")
    assert empty["page"] == empty["total_pages"] == 1
    assert empty["items"] == []
    assert empty["total"] == 0
    assert empty["scope_total"] == 100


def test_dates_include_whole_utc_days_and_exclude_next_midnight(journal):
    path, client = journal
    timestamps = [
        "2026-06-09T23:59:59.999999Z",
        "2026-06-10T00:00:00Z",
        "2026-06-10T23:59:59.999999Z",
        "2026-06-11T00:00:00Z",
        "2026-06-09T20:00:00-04:00",
        "2026-06-10T20:00:00-04:00",
        "2026-06-10T10:00:00",
    ]
    with sqlite3.connect(path) as connection:
        ids = [add_signal(connection, timestamp=value) for value in timestamps]
        fallback = add_signal(connection, timestamp=None, created_at="2026-06-10T17:00:00Z")
        add_signal(connection, timestamp="invalid", created_at="2026-06-10T17:00:00Z")
    result = search(client, "from=2026-06-10&to=2026-06-10")
    assert {row["id"] for row in result["items"]} == {ids[1], ids[2], ids[4], ids[6], fallback}
    assert ids[0] in {row["id"] for row in search(client, "to=2026-06-09")["items"]}
    assert ids[3] in {row["id"] for row in search(client, "from=2026-06-11")["items"]}


def test_maximum_date_does_not_overflow(journal):
    path, client = journal
    with sqlite3.connect(path) as connection:
        signal_id = add_signal(connection, timestamp="9999-12-31T23:59:59.999999Z")
    assert search(client, "from=9999-12-31&to=9999-12-31")["items"][0]["id"] == signal_id


def test_wait_filters_and_counts_apply_across_complete_scope(journal):
    path, client = journal
    with sqlite3.connect(path) as connection:
        for _ in range(510):
            add_signal(connection, direction="WAIT")
        add_signal(connection, direction="SHORT")
        add_signal(connection, ticker="OTHER", direction="WAIT")
    default = search(client, "ticker=AAA")
    assert default["total"] == 1
    assert default["hidden_wait_count"] == 510
    assert search(client, "ticker=AAA&include_wait=true")["total"] == 511
    explicit = search(client, "ticker=AAA&direction=WAIT")
    assert explicit["total"] == 510
    assert explicit["hidden_wait_count"] == 0
    assert search(client, "direction=LONG")["total"] == 0


def test_source_isolation_and_provenance_matched_outcomes_beyond_trade_cap(journal):
    path, client = journal
    with sqlite3.connect(path) as connection:
        live = add_signal(connection)
        replay = add_signal(connection, source="backtest", ticker="REPLAY")
        unknown = add_signal(connection, source=None, backend=None, account=None, ticker="LEGACY")
        for signal_id, source, backend, account, outcome in [
            (live, "live", "local", "paper", "LOSS"),
            (live, "live", "local", "paper", "WIN"),
            (live, "backtest", "local", "paper", "LOSS"),
            (live, "live", "alpaca", "paper", "LOSS"),
            (live, "live", "local", "other-account", "LOSS"),
            (replay, "backtest", "local", "paper", "OPEN"),
            (unknown, None, None, None, "BREAKEVEN"),
        ]:
            connection.execute(
                "INSERT INTO trades (signal_id, source, backend, account, outcome) VALUES (?, ?, ?, ?, ?)",
                (signal_id, source, backend, account, outcome),
            )
        connection.executemany("INSERT INTO trades (outcome) VALUES (?)", [("OPEN",)] * 550)
    result = search(client)
    assert result["scope_total"] == 1
    assert result["tickers"] == ["AAA"]
    assert [(row["id"], row["outcome"]) for row in result["items"]] == [(live, "WIN")]
    all_sources = search(client, "source=all")
    assert all_sources["scope_total"] == 3
    assert {row["id"]: row["outcome"] for row in all_sources["items"]} == {
        live: "WIN",
        replay: "OPEN",
        unknown: "BREAKEVEN",
    }
    assert search(client, "source=unknown")["items"][0]["id"] == unknown
    assert search(client, "ticker=REPLAY")["total"] == 0


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page=-1",
        "page=1.5",
        "page=2147483648",
        "page_size=0",
        "page_size=101",
        "page_size=no",
        "min_confidence=nan",
        "min_confidence=inf",
        "min_confidence=-0.1",
        "min_confidence=1.1",
        "min_confidence=no",
        "direction=BUY",
        "source=typo",
        "source=",
        "source=live&source=all",
        "include_wait=1",
        "from=2026-02-30",
        "to=2026-6-10",
        "from=2026-06-11&to=2026-06-10",
        "snapshot_id=-1",
        "snapshot_id=9007199254740992",
        "ticker=" + "A" * 33,
    ],
)
def test_rejects_invalid_queries(journal, query):
    _, client = journal
    response = client.get("/api/signals/search?" + query)
    assert response.status_code == 400
    assert "error" in response.get_json()
