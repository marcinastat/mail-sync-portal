from datetime import datetime, timezone

import pyotp
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from ..templating import templates
from passlib.hash import argon2
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_setup_complete
from ..models import AdminUser, TotpCredential
from ..services import totp_service
from ..services.audit_service import record
from ..services.auth_log import log_failed_login, log_successful_login

router = APIRouter(tags=["auth"], dependencies=[Depends(require_setup_complete)])


@router.get("/admin/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/admin/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(AdminUser).filter(AdminUser.username == username, AdminUser.is_active.is_(True)).first()
    if not user or not argon2.verify(password, user.password_hash):
        log_failed_login(client_ip(request), username)
        return templates.TemplateResponse(
            request, "login.html", {"error": "Nieprawidłowy login lub hasło."}, status_code=401
        )
    request.session["pending_totp_user_id"] = user.id
    return RedirectResponse("/admin/login/totp", status_code=303)


@router.get("/admin/login/totp")
def login_totp_form(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("pending_totp_user_id")
    if not user_id:
        return RedirectResponse("/admin/login", status_code=303)
    user = db.get(AdminUser, user_id)
    if user is None:
        request.session.clear()
        return RedirectResponse("/admin/login", status_code=303)
    # Nowe konto administracyjne (Ustawienia -> Użytkownicy) nie ma jeszcze
    # potwierdzonego TOTP — pierwsze logowanie zawsze wymusza enrollment,
    # tak samo jak konto z kreatora pierwszego uruchomienia.
    if user.totp is None or user.totp.confirmed_at is None:
        return RedirectResponse("/admin/login/totp-enroll", status_code=303)
    return templates.TemplateResponse(request, "login_totp.html", {})


@router.get("/admin/login/totp-enroll")
def login_totp_enroll_form(request: Request):
    if not request.session.get("pending_totp_user_id"):
        return RedirectResponse("/admin/login", status_code=303)
    return templates.TemplateResponse(request, "login_totp_enroll.html", {})


@router.get("/admin/login/totp-enroll/qr")
def login_totp_enroll_qr(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("pending_totp_user_id")
    if not user_id:
        return RedirectResponse("/admin/login", status_code=303)
    user = db.get(AdminUser, user_id)
    secret = request.session.get("pending_totp_enroll_secret")
    if not secret:
        secret = totp_service.generate_secret()
        request.session["pending_totp_enroll_secret"] = secret
    png = totp_service.provisioning_qr_png(secret, account_name=user.username if user else "admin")
    return Response(content=png, media_type="image/png")


@router.post("/admin/login/totp-enroll")
def login_totp_enroll_submit(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    user_id = request.session.get("pending_totp_user_id")
    secret = request.session.get("pending_totp_enroll_secret")
    if not user_id or not secret:
        return RedirectResponse("/admin/login", status_code=303)
    user = db.get(AdminUser, user_id)
    if user is None:
        request.session.clear()
        return RedirectResponse("/admin/login", status_code=303)

    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        return templates.TemplateResponse(
            request, "login_totp_enroll.html", {"error": "Nieprawidłowy kod."}, status_code=400
        )

    recovery_codes = totp_service.generate_recovery_codes()
    db.add(
        TotpCredential(
            admin_user_id=user.id,
            secret_encrypted=totp_service.encrypt_secret(secret),
            confirmed_at=datetime.now(timezone.utc),
            recovery_codes_hashed=totp_service.hash_recovery_codes(recovery_codes),
        )
    )
    request.session.pop("pending_totp_enroll_secret", None)
    request.session["pending_recovery_codes"] = recovery_codes
    return RedirectResponse("/admin/login/totp-enroll/recovery-codes", status_code=303)


@router.get("/admin/login/totp-enroll/recovery-codes")
def login_totp_enroll_recovery_codes(request: Request, db: Session = Depends(get_db)):
    codes = request.session.pop("pending_recovery_codes", None)
    user_id = request.session.get("pending_totp_user_id")
    if not codes or not user_id:
        return RedirectResponse("/admin/login", status_code=303)
    user = db.get(AdminUser, user_id)
    request.session.pop("pending_totp_user_id", None)
    request.session["admin_user_id"] = user.id
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    record(db, actor_admin_user_id=user.id, action="auth.totp_enrolled", source_ip=client_ip(request))
    log_successful_login(client_ip(request), user.username)
    return templates.TemplateResponse(request, "login_totp_enroll_recovery.html", {"codes": codes})


@router.post("/admin/login/totp")
def login_totp_submit(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    user_id = request.session.get("pending_totp_user_id")
    if not user_id:
        return RedirectResponse("/admin/login", status_code=303)
    user = db.get(AdminUser, user_id)
    if user is None or user.totp is None or user.totp.confirmed_at is None:
        request.session.clear()
        return RedirectResponse("/admin/login", status_code=303)

    ok = totp_service.verify_code(user.totp.secret_encrypted, code)
    if not ok:
        recovery_index = totp_service.verify_recovery_code(user.totp.recovery_codes_hashed, code)
        if recovery_index is not None:
            ok = True
            remaining = list(user.totp.recovery_codes_hashed)
            remaining.pop(recovery_index)
            user.totp.recovery_codes_hashed = remaining
            db.add(user.totp)

    if not ok:
        log_failed_login(client_ip(request), user.username)
        return templates.TemplateResponse(
            request, "login_totp.html", {"error": "Nieprawidłowy kod."}, status_code=401
        )

    request.session.pop("pending_totp_user_id", None)
    request.session["admin_user_id"] = user.id
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    record(
        db,
        actor_admin_user_id=user.id,
        action="auth.login_success",
        source_ip=client_ip(request),
    )
    log_successful_login(client_ip(request), user.username)
    return RedirectResponse("/admin/", status_code=303)


@router.post("/admin/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("admin_user_id")
    if user_id:
        record(db, actor_admin_user_id=user_id, action="auth.logout", source_ip=client_ip(request))
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
