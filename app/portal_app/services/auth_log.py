import logging
from pathlib import Path

_LOG_PATH = Path("/var/log/portal/auth.log")

_logger = logging.getLogger("portal.auth")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(_LOG_PATH)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        _logger.addHandler(handler)
    except OSError:
        # Katalog logów tworzony przez scripts/vm1/50-portal-app.sh; jeśli
        # proces nie ma jeszcze do niego dostępu (np. test lokalny), nie
        # wywracamy aplikacji — logowanie po prostu trafia tylko do stdout.
        pass


def log_failed_login(ip: str | None, username: str) -> None:
    _logger.info("IP=%s user=%s result=failed", ip or "unknown", username)


def log_successful_login(ip: str | None, username: str) -> None:
    _logger.info("IP=%s user=%s result=success", ip or "unknown", username)
