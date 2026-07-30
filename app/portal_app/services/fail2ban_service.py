"""Status fail2ban do panelu (Raporty). VM1 czytamy lokalnie przez sudo-helper
(fail2ban-client wymaga roota — socket /var/run/fail2ban), VM2 przez vm2-api.
Parsujemy SUROWE wyjście fail2ban-client. Widok jest READ-ONLY — unban/ban robi
się z konsoli (patrz docs/technical/runbooks/fail2ban.md)."""

import re
import subprocess

HELPER = "/opt/portal-app/bin/fail2ban-status.sh"

_RE = {
    "currently_failed": re.compile(r"Currently failed:\s*(\d+)"),
    "total_failed": re.compile(r"Total failed:\s*(\d+)"),
    "currently_banned": re.compile(r"Currently banned:\s*(\d+)"),
    "total_banned": re.compile(r"Total banned:\s*(\d+)"),
}
_BANNED_IPS = re.compile(r"Banned IP list:\s*(.*)")


def parse(text: str) -> dict:
    """Zamienia surowe wyjście helpera (STATE + bloki '=== JAIL x ===') na dict:
    {state, jails:[{name, currently_failed, total_failed, currently_banned,
    total_banned, banned_ips:[...]}]}."""
    state = "unknown"
    jails: list[dict] = []
    cur: dict | None = None
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("STATE "):
            state = s.split(" ", 1)[1]
            continue
        if s.startswith("=== JAIL "):
            cur = {"name": s[len("=== JAIL "):].rstrip(" ="), "currently_failed": 0,
                   "total_failed": 0, "currently_banned": 0, "total_banned": 0, "banned_ips": []}
            jails.append(cur)
            continue
        if cur is None:
            continue
        for key, rx in _RE.items():
            m = rx.search(line)
            if m:
                cur[key] = int(m.group(1))
                break
        else:
            m = _BANNED_IPS.search(line)
            if m:
                cur["banned_ips"] = m.group(1).split()
    return {"state": state, "jails": jails}


def local_status() -> dict:
    """Status fail2ban na VM1 (przez sudo-helper, read-only)."""
    try:
        out = subprocess.run(["sudo", "-n", HELPER], capture_output=True, text=True, timeout=10)
        if out.returncode != 0 and not out.stdout:
            return {"state": "error", "jails": []}
        return parse(out.stdout)
    except Exception:
        return {"state": "error", "jails": []}
