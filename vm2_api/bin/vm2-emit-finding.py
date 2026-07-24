#!/usr/bin/env python3.12
"""Emiter linii findings.jsonl dla ClamAV — uruchamiany JAKO ROOT ze skanu (może
czytać maildiry 0600 vmail). Czyta i DEKODUJE nagłówki maila (Subject/From/Date,
MIME-encoded words), wylicza skrzynkę ze ścieżki i wypisuje JSON. Nagłówki
zapisujemy w momencie wykrycia — API (konto vm2-api) nie ma dostępu do plików
poczty, a i tak plik może później zniknąć.

  FSIG=<sygnatura> FENGINE=clamav FSEV=malware vm2-emit-finding.py <ścieżka>
"""
import datetime
import email
import email.header
import json
import os
import sys


def read_headers(path):
    try:
        head = b""
        with open(path, "rb") as fh:
            for line in fh:
                if line in (b"\r\n", b"\n"):
                    break
                head += line
                if len(head) > 65536:
                    break
        msg = email.message_from_bytes(head)

        def dec(name):
            v = msg.get(name)
            if not v:
                return None
            out = ""
            for txt, enc in email.header.decode_header(v):
                out += txt.decode(enc or "utf-8", "replace") if isinstance(txt, bytes) else txt
            return out.strip() or None

        return dec("subject"), dec("from"), dec("date")
    except Exception:
        return None, None, None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    sig = os.environ.get("FSIG", "")
    engine = os.environ.get("FENGINE", "clamav")
    sev = os.environ.get("FSEV", "malware")
    subject, frm, dt = read_headers(path)
    rel = path.split("/vhosts/", 1)[1] if "/vhosts/" in path else path
    parts = rel.split("/")
    mailbox = (parts[1] + "@" + parts[0]) if len(parts) >= 2 else "?"
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(json.dumps({
        "ts": ts, "engine": engine, "mailbox": mailbox, "path": path,
        "signature": sig, "severity": sev,
        "subject": subject, "from": frm, "date": dt,
    }))


if __name__ == "__main__":
    main()
