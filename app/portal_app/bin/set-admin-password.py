"""Pomocnik CLI ustawiający hash hasła admina panelu — uruchamiany JAKO
portal-app (przez wrapper portal-admin-password.sh: `runuser -u portal-app`),
żeby mieć dostęp do pliku hasła bazy i użyć TEGO SAMEGO argon2 co logowanie.

Wejście:
  env PORTAL_USER  — login admina (nie jest sekretem)
  env PORTAL_LIST  — jeśli ustawione: wypisz loginy i zakończ
  STDIN            — nowe hasło (przez potok, NIE argv/env — nie wycieka do `ps`)
"""

import os
import sys

sys.path.insert(0, "/opt/portal-app")

from passlib.hash import argon2  # noqa: E402

from portal_app.db import session_scope  # noqa: E402
from portal_app.models import AdminUser  # noqa: E402


def main() -> int:
    if os.environ.get("PORTAL_LIST"):
        with session_scope() as db:
            for u in db.query(AdminUser).order_by(AdminUser.username):
                print(f"{u.username}\t{'aktywny' if u.is_active else 'nieaktywny'}")
        return 0

    username = os.environ.get("PORTAL_USER", "").strip()
    new_password = sys.stdin.read().rstrip("\n")
    if not username or not new_password:
        print("Brak loginu lub hasła.", file=sys.stderr)
        return 2

    with session_scope() as db:
        user = db.query(AdminUser).filter(AdminUser.username == username).first()
        if user is None:
            print(f"Nie ma admina o loginie '{username}'.", file=sys.stderr)
            return 3
        user.password_hash = argon2.hash(new_password)
        db.add(user)
    print(f"Hasło admina '{username}' zostało zmienione.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
