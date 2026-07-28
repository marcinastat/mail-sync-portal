"""Pomocnik CLI resetujący TOTP admina panelu — uruchamiany JAKO portal-app
(przez wrapper portal-admin-totp-reset.sh: `runuser -u portal-app`), żeby mieć
dostęp do pliku hasła bazy i tego samego szyfrowania/audytu co aplikacja.

Reset = usunięcie wiersza totp_credentials. Logika logowania
(routers/auth.py) wymusza świeży enrollment, gdy `user.totp is None` lub
`confirmed_at is None`, więc po resecie użytkownik przy następnym logowaniu
paruje TOTP od nowa (nowy sekret, QR, kody odzyskiwania). Używać, gdy admin
stracił authenticator (samo zresetowanie hasła nie odblokuje — TOTP nadal
wymagane).

Wejście:
  env PORTAL_USER  — login admina (nie jest sekretem)
  env PORTAL_LIST  — jeśli ustawione: wypisz adminów + status TOTP i zakończ
"""

import os
import sys

sys.path.insert(0, "/opt/portal-app")

from portal_app.db import session_scope  # noqa: E402
from portal_app.models import AdminUser, TotpCredential  # noqa: E402
from portal_app.services import audit_service  # noqa: E402


def main() -> int:
    if os.environ.get("PORTAL_LIST"):
        with session_scope() as db:
            for u in db.query(AdminUser).order_by(AdminUser.username):
                paired = u.totp is not None and u.totp.confirmed_at is not None
                status = "TOTP:sparowany" if paired else "TOTP:brak"
                print(f"{u.username}\t{'aktywny' if u.is_active else 'nieaktywny'}\t{status}")
        return 0

    username = os.environ.get("PORTAL_USER", "").strip()
    if not username:
        print("Brak loginu.", file=sys.stderr)
        return 2

    with session_scope() as db:
        user = db.query(AdminUser).filter(AdminUser.username == username).first()
        if user is None:
            print(f"Nie ma admina o loginie '{username}'.", file=sys.stderr)
            return 3

        deleted = db.query(TotpCredential).filter(
            TotpCredential.admin_user_id == user.id
        ).delete(synchronize_session=False)

        # Ślad w audycie (append-only, hash-chained). Actor=None oznacza akcję
        # systemową/konsolową; target to zresetowane konto admina.
        audit_service.record(
            db,
            actor_admin_user_id=None,
            action="auth.totp_reset_console",
            target_type="admin_user",
            target_id=str(user.id),
            details={"username": user.username, "origin": "root-cli", "had_totp": bool(deleted)},
            source_ip=None,
        )

    if deleted:
        print(f"TOTP admina '{username}' zresetowany — przy następnym logowaniu sparuje od nowa.")
    else:
        print(f"Admin '{username}' i tak nie miał sparowanego TOTP — przy następnym logowaniu i tak nastąpi enrollment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
