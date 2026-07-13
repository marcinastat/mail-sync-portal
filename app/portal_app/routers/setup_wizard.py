from datetime import datetime, timezone
from pathlib import Path

import pyotp
from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from ..templating import templates
from passlib.hash import argon2
from sqlalchemy.orm import Session

from ..deps import get_db, get_instance_state
from ..models import AdminUser, BrandingConfig, TotpCredential, Vm2Connection
from ..services import branding_renderer, totp_service, vm2_client
from ..services.audit_service import record

router = APIRouter(prefix="/admin/setup", tags=["setup"])

ADMIN_SUBNET_FILE = Path("/etc/portal/admin-subnet-cidr")


@router.get("")
def setup_entry(request: Request, state=Depends(get_instance_state)):
    if not state.first_run_required:
        return RedirectResponse("/admin/", status_code=303)
    step = state.setup_step_completed
    pages = ["setup_account.html", "setup_totp.html", "setup_subnet.html", "setup_vm2.html", "setup_branding.html"]
    if step >= len(pages):
        return RedirectResponse("/admin/setup/finish", status_code=303)
    ctx = {"step": step}
    if step == 2:
        ctx["admin_subnet_cidr"] = (
            ADMIN_SUBNET_FILE.read_text().strip() if ADMIN_SUBNET_FILE.exists() else "(nieznana — sprawdź install.conf na serwerze)"
        )
    return templates.TemplateResponse(request, f"setup_wizard/{pages[step]}", ctx)


@router.post("/account")
def setup_account(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    state=Depends(get_instance_state),
):
    if state.setup_step_completed != 0:
        return RedirectResponse("/admin/setup", status_code=303)
    user = AdminUser(username=username, email=email, password_hash=argon2.hash(password), role="admin")
    db.add(user)
    db.flush()
    request.session["setup_admin_user_id"] = user.id
    state.setup_step_completed = 1
    db.add(state)
    return RedirectResponse("/admin/setup", status_code=303)


@router.get("/totp/qr")
def setup_totp_qr(request: Request):
    secret = request.session.get("setup_totp_secret")
    if not secret:
        secret = totp_service.generate_secret()
        request.session["setup_totp_secret"] = secret
    png = totp_service.provisioning_qr_png(secret, account_name="admin")
    return Response(content=png, media_type="image/png")


@router.post("/totp")
def setup_totp_confirm(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db),
    state=Depends(get_instance_state),
):
    if state.setup_step_completed != 1:
        return RedirectResponse("/admin/setup", status_code=303)
    user_id = request.session.get("setup_admin_user_id")
    secret = request.session.get("setup_totp_secret")
    user = db.get(AdminUser, user_id) if user_id else None
    if not user or not secret:
        return RedirectResponse("/admin/setup", status_code=303)

    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        return templates.TemplateResponse(
            request, "setup_wizard/setup_totp.html", {"step": 1, "error": "Nieprawidłowy kod."}, status_code=400
        )

    recovery_codes = totp_service.generate_recovery_codes()
    totp = TotpCredential(
        admin_user_id=user.id,
        secret_encrypted=totp_service.encrypt_secret(secret),
        confirmed_at=datetime.now(timezone.utc),
        recovery_codes_hashed=totp_service.hash_recovery_codes(recovery_codes),
    )
    db.add(totp)
    request.session.pop("setup_totp_secret", None)
    request.session["setup_recovery_codes"] = recovery_codes
    state.setup_step_completed = 2
    db.add(state)
    return RedirectResponse("/admin/setup/totp/recovery-codes", status_code=303)


@router.get("/totp/recovery-codes")
def show_recovery_codes(request: Request):
    codes = request.session.pop("setup_recovery_codes", None)
    if not codes:
        return RedirectResponse("/admin/setup", status_code=303)
    return templates.TemplateResponse(request, "setup_wizard/setup_totp_recovery.html", {"codes": codes})


@router.post("/subnet")
def setup_subnet_confirm(state=Depends(get_instance_state), db: Session = Depends(get_db)):
    if state.setup_step_completed != 2:
        return RedirectResponse("/admin/setup", status_code=303)
    state.setup_step_completed = 3
    db.add(state)
    return RedirectResponse("/admin/setup", status_code=303)


@router.post("/vm2")
def setup_vm2(
    request: Request,
    vm2_host: str = Form(...),
    vm2_api_port: int = Form(8443),
    db: Session = Depends(get_db),
    state=Depends(get_instance_state),
):
    if state.setup_step_completed != 3:
        return RedirectResponse("/admin/setup", status_code=303)
    conn = db.query(Vm2Connection).first() or Vm2Connection()
    conn.vm2_host = vm2_host
    conn.vm2_api_port = vm2_api_port
    db.add(conn)
    db.flush()

    try:
        health = vm2_client.check_health(conn)
    except vm2_client.Vm2ApiError as exc:
        return templates.TemplateResponse(
            request,
            "setup_wizard/setup_vm2.html",
            {"step": 3, "error": f"Nie udało się połączyć z VM2: {exc}"},
            status_code=400,
        )

    conn.last_health_check_ok = bool(health.get("healthy"))
    db.add(conn)
    state.setup_step_completed = 4
    db.add(state)
    return RedirectResponse("/admin/setup", status_code=303)


@router.post("/branding")
def setup_branding(
    request: Request,
    primary_color: str = Form("#2563eb"),
    secondary_color: str = Form("#1e293b"),
    accent_color: str = Form("#f59e0b"),
    logo: UploadFile | None = None,
    db: Session = Depends(get_db),
    state=Depends(get_instance_state),
):
    if state.setup_step_completed != 4:
        return RedirectResponse("/admin/setup", status_code=303)
    branding = db.query(BrandingConfig).first() or BrandingConfig()
    branding.primary_color = primary_color
    branding.secondary_color = secondary_color
    branding.accent_color = accent_color
    if logo is not None and logo.filename:
        logo_path = branding_renderer.save_logo(logo.file.read())
        branding.logo_path = logo_path
    db.add(branding)
    db.flush()
    branding_renderer.render_all(branding)

    state.first_run_required = False
    state.setup_step_completed = 5
    db.add(state)

    admin_user_id = request.session.get("setup_admin_user_id")
    record(db, actor_admin_user_id=admin_user_id, action="setup.completed")
    request.session.pop("setup_admin_user_id", None)
    return RedirectResponse("/admin/login", status_code=303)
