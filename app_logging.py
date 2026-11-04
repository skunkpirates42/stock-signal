import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / ".live-logs"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
MAX_LOG_BYTES = 5_000_000
ROTATED_LOG_COUNT = 5


def configure_logging(process_name: str, log_dir: Path = LOG_DIR) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)
    console = logging.StreamHandler()
    # Console output for people stays the entry point's own prints; stderr only
    # carries problems. The file holds the full event timeline.
    console.setLevel(logging.WARNING)
    console.setFormatter(formatter)
    root.addHandler(console)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = RotatingFileHandler(
            log_dir / f"{process_name}.log",
            maxBytes=MAX_LOG_BYTES,
            backupCount=ROTATED_LOG_COUNT,
        )
    except OSError as exc:
        log_event(root, "log_file_unavailable", logging.WARNING, path=log_dir, error=exc)
        return
    log_file.setFormatter(formatter)
    root.addHandler(log_file)


def format_event(event: str, fields: dict[str, object]) -> str:
    return " ".join([event] + [f"{key}={_format_value(value)}" for key, value in fields.items()])


def _format_value(value: object) -> str:
    text = str(value)
    if not text or any(character.isspace() or character in '"=' for character in text):
        return json.dumps(text)
    return text


def log_event(
    logger: logging.Logger, event: str, level: int = logging.INFO, **fields: object
) -> None:
    if not logger.isEnabledFor(level):
        return
    try:
        message = format_event(event, fields)
    except Exception:
        # Logging is observational; a field that cannot be rendered must not
        # interrupt trading.
        message = f"{event} fields_unrenderable=True"
    logger.log(level, "%s", message)
