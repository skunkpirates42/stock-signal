import logging
import re

import pytest

from app_logging import configure_logging, format_event, log_event


@pytest.fixture
def isolated_root_logger():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers = []
    yield root
    for handler in root.handlers:
        handler.close()
    root.handlers, root.level = saved_handlers, saved_level


def test_event_values_with_spaces_or_equals_are_quoted():
    line = format_event("x", {"a": 1, "b": "two words", "c": "k=v", "d": None, "e": ""})
    assert line == 'x a=1 b="two words" c="k=v" d=None e=""'


def test_unrenderable_field_does_not_raise(caplog):
    class Unrenderable:
        def __str__(self):
            raise RuntimeError("boom")

    caplog.set_level(logging.INFO)
    log_event(logging.getLogger("t"), "evt", value=Unrenderable())
    assert caplog.records[-1].getMessage() == "evt fields_unrenderable=True"


def test_file_gets_info_and_console_only_warnings(tmp_path, isolated_root_logger, capsys):
    configure_logging("unit", log_dir=tmp_path)
    log_event(logging.getLogger("t"), "routine", n=1)
    log_event(logging.getLogger("t"), "problem", logging.WARNING, reason="bad")
    text = (tmp_path / "unit.log").read_text()
    assert re.search(r"INFO t routine n=1$", text, re.M)
    assert re.search(r"WARNING t problem reason=bad$", text, re.M)
    err = capsys.readouterr().err
    assert "problem" in err and "routine" not in err


def test_unwritable_log_dir_falls_back_to_console(tmp_path, isolated_root_logger, capsys):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    configure_logging("unit", log_dir=blocker)
    assert "log_file_unavailable" in capsys.readouterr().err
    log_event(logging.getLogger("t"), "still_runs", logging.WARNING)
    assert "still_runs" in capsys.readouterr().err
