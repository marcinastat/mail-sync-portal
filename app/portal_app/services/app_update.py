"""Aktualizacja APLIKACJI portalu z panelu (kod VM1 + API VM2 z GitHub).

Root-helper portal-app-update.sh (scripts/app-update-helper.sh) uruchamia w tle
transient unit, który aktualizuje najpierw VM2 (przez jej API, mTLS), potem VM1
(scripts/update.sh — to samo co z konsoli). Unit przeżywa restart panelu w
trakcie i zamknięcie przeglądarki; panel tylko startuje i odczytuje stan
(/var/lib/portal-update/app-run + ogon logu). Sudoers: tylko check/start/status."""

import subprocess

from . import vm2_client

HELPER = "/opt/portal-app/bin/portal-app-update.sh"
_VERSION_KEYS = ("local", "local_date", "local_subject")


def _helper(mode: str, timeout: int = 60) -> tuple[dict, str]:
    res = subprocess.run(["/usr/bin/sudo", "-n", HELPER, mode], capture_output=True, text=True, timeout=timeout)
    head, _, log = res.stdout.partition("---log---\n")
    kv = {}
    for line in head.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            kv[key.strip()] = value.strip()
    if res.returncode != 0 and "error" not in kv:
        kv["error"] = (res.stderr or res.stdout).strip()[-500:] or "Błąd helpera aktualizacji aplikacji."
    return kv, log


def check(conn) -> dict:
    """Wersje kodu: VM1, VM2 i najnowsza na GitHub (do karty w panelu)."""
    vm1, _ = _helper("check")
    out = {
        "vm1": {"error": vm1["error"]} if "error" in vm1 else {k: vm1.get(k) or None for k in _VERSION_KEYS},
        "remote": vm1.get("remote") or None,
        "vm2": None,
    }
    if conn is not None and conn.vm2_host:
        try:
            out["vm2"] = vm2_client.app_update_check(conn)
        except vm2_client.Vm2ApiError as exc:
            out["vm2"] = {"error": (
                "VM2 nie obsługuje jeszcze aktualizacji z panelu — zaktualizuj ją raz z konsoli (scripts/update.sh)."
                if exc.status_code == 404 else str(exc))}
    return out


def start() -> None:
    kv, _ = _helper("start")
    if "error" in kv:
        raise RuntimeError(kv["error"])


def status() -> dict:
    """Stan w kształcie przebiegu aktualizacji (ten sam modal co dnf/Roundcube)."""
    kv, log = _helper("status")
    state = kv.get("state", "none")
    active = kv.get("active") == "yes"
    error = None
    if state == "running" and not active:
        # Proces aktualizacji już nie działa, a nie zapisał wyniku (np. reboot VM1).
        state, error = "failed", "Przebieg przerwany — proces aktualizacji nie działa. Sprawdź log na VM1."
    elif state == "failed":
        error = f"Aktualizacja aplikacji nieudana (etap: {kv.get('step') or '?'}) — przyczyna w wyjściu powyżej."
    elif "error" in kv:
        state, error = "failed", kv["error"]
    return {
        "id": "app",
        "host": "app",
        "mode": "app",
        "status": state if state in ("running", "success", "failed") else "none",
        "phase": kv.get("step") or "start",
        "output": log,
        "started_at": kv.get("started") or None,
        "finished_at": kv.get("updated") if state in ("success", "failed") else None,
        "error": error,
        "log_path": kv.get("log") or None,
        "healthy": None,
        "reboot_needed": None,
        "backup_path": None,
    }
