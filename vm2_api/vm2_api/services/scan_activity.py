"""Aktywność skanów maildirów (ClamAV / rspamd) do kafelka VM2 w panelu:
kiedy był OSTATNI przebieg, ile plików przeskanowano (ostatni przebieg / łącznie)
i kiedy będzie NASTĘPNY (z timera systemd). Skrypty skanujące (root) zapisują
`/var/lib/vm2-scan/scan-stats-<engine>` po każdym przebiegu; API tylko czyta.

Następny skan liczymy z `NextElapseUSecMonotonic` timera — systemctl podaje go
jako czas monotoniczny sformatowany ("1d 17h 22min 32s"), więc parsujemy do
sekund i odejmujemy bieżący `time.monotonic()` (ten sam zegar CLOCK_MONOTONIC),
co daje ile zostało do następnego uruchomienia. Timery są monotoniczne
(OnUnitActiveSec), więc NextElapseUSecRealtime jest puste — stąd ta droga."""

import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_DIR = Path("/var/lib/vm2-scan")

_UNITS = {
    "us": 1e-6, "ms": 1e-3, "s": 1, "sec": 1, "min": 60,
    "h": 3600, "hr": 3600, "d": 86400, "w": 604800, "month": 2629800, "y": 31557600,
}


def _parse_duration(s: str) -> float | None:
    """Sekundy z formatu systemd ('1d 17h 22min 32.2s', '26min 3s', '500ms')."""
    total = 0.0
    for num, unit in re.findall(r"([\d.]+)\s*(us|ms|sec|s|min|h|hr|d|w|month|y)", s or ""):
        total += float(num) * _UNITS[unit]
    return total or None


def next_run(timer: str) -> datetime | None:
    try:
        out = subprocess.run(
            ["systemctl", "show", timer, "-p", "NextElapseUSecMonotonic", "--value"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        mono = _parse_duration(out)
        if mono is None:
            return None
        secs = mono - time.monotonic()
        if secs < -5:  # timer w przeszłości / niespójność — nie zgadujemy
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=max(0.0, secs))
    except Exception:
        return None


def read_stats(engine: str) -> dict:
    data = {"last_scan_at": None, "last_scan_count": None, "last_scan_found": None, "total_scanned": None}
    try:
        kv: dict[str, str] = {}
        for line in (STATE_DIR / f"scan-stats-{engine}").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip()
        if "ts" in kv:
            data["last_scan_at"] = datetime.fromtimestamp(int(kv["ts"]), tz=timezone.utc)
        if "last" in kv:
            data["last_scan_count"] = int(kv["last"])
        if "found" in kv:
            data["last_scan_found"] = int(kv["found"])
        if "total" in kv:
            data["total_scanned"] = int(kv["total"])
    except Exception:
        pass
    return data


def activity(engine: str, timer: str) -> dict:
    d = read_stats(engine)
    d["next_scan_at"] = next_run(timer)
    return d
