#!/usr/bin/env python3.12
"""Parser wyniku `rspamc -j` (na stdin) -> linia findings.jsonl (na stdout) albo
nic. Emituje TYLKO phishing/odrzucenia (nie zwykły spam — stare newslettery to
szum). Ścieżka pliku w env FPATH."""
import datetime
import json
import os
import sys

raw = sys.stdin.read()
if not raw.strip():
    sys.exit(0)
try:
    d = json.loads(raw)
except Exception:
    sys.exit(0)

res = d.get("default") if isinstance(d, dict) and "default" in d else d
res = res or {}
symbols = res.get("symbols", {}) or {}
action = res.get("action", "") or ""
score = res.get("score", 0) or 0

phish = [s for s in symbols if "PHISH" in s.upper()]
is_reject = action in ("reject", "rewrite subject", "add header")
if not phish and not is_reject:
    sys.exit(0)

sig = phish[0] if phish else (action or "suspicious")
sev = "phishing" if phish else "spam"
path = os.environ.get("FPATH", "")
rel = path[len("/var/mail/vhosts/"):] if path.startswith("/var/mail/vhosts/") else path
parts = rel.split("/")
mailbox = (parts[1] + "@" + parts[0]) if len(parts) >= 2 else "?"
ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
print(json.dumps({
    "ts": ts, "engine": "rspamd", "mailbox": mailbox, "path": path,
    "signature": f"{sig} (score {round(float(score), 1)})", "severity": sev,
}))
