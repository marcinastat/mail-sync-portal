"""Aktualizacja Roundcube z panelu (VM1).

Roundcube jest instalowany z oficjalnej paczki, nie z dnf — aktualizuje go
root-helper roundcube-upgrade.sh (to samo narzędzie, co z konsoli: podpis GPG,
kopia plików i bazy, test, automatyczny rollback). Panel ma do niego tylko dwa
tryby bez argumentów (sudoers): `status` i `upgrade-panel` — zawsze najnowsza
wersja w bieżącej gałęzi. Zmiana gałęzi i ręczny rollback zostają na konsoli.

`status` jest szybki (cache listy wydań) i idzie z żądania web (AJAX);
`run_upgrade` trwa minuty — wyłącznie z portal-workera."""

import subprocess

HELPER = "/opt/portal-app/bin/roundcube-upgrade.sh"


def _kv(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("["):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def status() -> dict:
    res = subprocess.run(["/usr/bin/sudo", "-n", HELPER, "status"], capture_output=True, text=True, timeout=60)
    kv = _kv(res.stdout)
    if res.returncode != 0 or not kv.get("installed"):
        return {"error": (res.stderr or res.stdout).strip()[-500:] or "Nie udało się odczytać wersji Roundcube."}
    return {
        "installed": kv["installed"],
        "latest_branch": kv.get("latest_branch") or None,
        "latest": kv.get("latest") or None,
    }


def run_upgrade() -> dict:
    res = subprocess.run(["/usr/bin/sudo", "-n", HELPER, "upgrade-panel"],
                         capture_output=True, text=True, timeout=1800)
    output = res.stdout + res.stderr
    return {"output": output, "ok": res.returncode == 0, "backup_path": _kv(output).get("backup_path")}
