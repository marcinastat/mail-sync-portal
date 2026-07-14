from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import get_session
from .models import AdminUser, InstanceState


def get_db() -> Iterator[Session]:
    yield from get_session()


def get_instance_state(db: Session = Depends(get_db)) -> InstanceState:
    state = db.query(InstanceState).first()
    if state is None:
        state = InstanceState()
        db.add(state)
        db.flush()
    return state


def require_setup_complete(state: InstanceState = Depends(get_instance_state)) -> None:
    if state.first_run_required:
        raise HTTPException(status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/setup"})


def require_login(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    user_id = request.session.get("admin_user_id")
    if not user_id:
        raise HTTPException(status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    user = db.get(AdminUser, user_id)
    if user is None or not user.is_active:
        request.session.clear()
        raise HTTPException(status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    return user


def client_ip(request: Request) -> str | None:
    """Realny adres klienta do audytu / fail2ban.

    nginx proxuje do gunicorna przez gniazdo UNIX (/run/portal-app/gunicorn.sock),
    więc połączenie nie ma peera TCP — `request.client.host` jest wtedy None/puste
    i audit log zapisywał NULL. Prawdziwy adres wstrzykuje nginx w nagłówek
    `X-Real-IP` ($remote_addr). Zaufanie do tego nagłówka jest tu bezpieczne:
    do gniazda gunicorna może się połączyć WYŁĄCZNIE lokalny nginx (klient z
    zewnątrz nie dosięgnie socketu, więc nie podrobi nagłówka). X-Forwarded-For
    trzymamy jako zapas na wypadek zmiany konfiguracji na proxy TCP."""
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
