from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from ..templating import templates
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, TlsConfig
from ..services import acmedns_service, tls_manager
from ..services.audit_service import record

router = APIRouter(prefix="/admin/settings/tls", tags=["settings-tls"], dependencies=[Depends(require_setup_complete)])


def _get_config(db: Session) -> TlsConfig:
    config = db.query(TlsConfig).first()
    if config is None:
        config = TlsConfig()
        db.add(config)
        db.flush()
    return config


def _tls_context(db: Session, current_user: AdminUser, **extra) -> dict:
    acme = acmedns_service.get_config(db)
    ctx = {
        "active": "settings",
        "current_user": current_user,
        "config": _get_config(db),
        "acme": acme,
        "acme_instructions": acmedns_service.dns_instructions(acme) if acme else None,
    }
    ctx.update(extra)
    return ctx


@router.get("")
def show(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "settings/tls.html", _tls_context(db, current_user))


@router.post("/acme-dns/register")
def acme_dns_register(
    request: Request,
    acme_dns_server: str = Form(...),
    hostname: str = Form(...),
    a_record_ip: str = Form(""),
    restrict_to_ip: str = Form(""),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    allowfrom = [restrict_to_ip.strip()] if restrict_to_ip.strip() else None
    try:
        cfg = acmedns_service.register(
            db,
            server=acme_dns_server,
            hostname=hostname,
            a_record_ip=a_record_ip,
            allowfrom=allowfrom,
        )
    except acmedns_service.AcmeDnsError as exc:
        return templates.TemplateResponse(
            request, "settings/tls.html",
            _tls_context(db, current_user, acme_error=str(exc)),
            status_code=400,
        )
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="tls.acmedns_register",
        target_type="acme_dns",
        target_id=cfg.hostname,
        details={"server": cfg.acme_dns_server, "fulldomain": cfg.fulldomain},
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/settings/tls?acme_registered=1", status_code=303)


@router.get("/acme-dns/status")
def acme_dns_status(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    """Fragment statusu acme-dns (HTMX) — auto-load + polling z karty TLS."""
    cfg = acmedns_service.get_config(db)
    if cfg is None:
        return HTMLResponse("")
    return templates.TemplateResponse(
        request, "settings/_acme_status.html", {"acme": cfg, "st": acmedns_service.status(cfg)}
    )


@router.post("/acme-dns/issue")
def acme_dns_issue(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    """Wystawia cert Let's Encrypt przez acme-dns i przełącza nginx (root-helper,
    systemd-run escape). Synchronicznie (~15-30 s dla acme-dns)."""
    cfg = acmedns_service.get_config(db)
    if cfg is None:
        return RedirectResponse("/admin/settings/tls", status_code=303)
    ok, msg = acmedns_service.issue_certificate(cfg)
    if ok:
        config = _get_config(db)
        config.mode = "certbot"
        from datetime import datetime, timezone
        config.certbot_last_success_at = datetime.now(timezone.utc)
        db.add(config)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="tls.acmedns_issue" + ("" if ok else "_failed"),
        target_type="acme_dns",
        target_id=cfg.hostname,
        details={"ok": ok, "output_tail": msg[-500:]},
        source_ip=client_ip(request),
    )
    if ok:
        return RedirectResponse("/admin/settings/tls?acme_issued=1", status_code=303)
    return templates.TemplateResponse(
        request, "settings/tls.html",
        _tls_context(db, current_user, acme_error=f"Wystawienie certyfikatu nie powiodło się: {msg}"),
        status_code=400,
    )


@router.post("/manual")
def apply_manual(
    request: Request,
    cert_pem: str = Form(...),
    key_pem: str = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    config = _get_config(db)
    try:
        tls_manager.validate_and_stage(cert_pem, key_pem)
        tls_manager.switch_mode("manual")
    except tls_manager.TlsValidationError as exc:
        return templates.TemplateResponse(
            request, "settings/tls.html", {"active": "settings", "current_user": current_user, "config": config, "error": str(exc)}, status_code=400
        )

    from datetime import datetime, timezone

    config.mode = "manual"
    config.manual_uploaded_at = datetime.now(timezone.utc)
    db.add(config)
    record(db, actor_admin_user_id=current_user.id, action="tls.switch_manual", source_ip=client_ip(request))
    return RedirectResponse("/admin/settings/tls", status_code=303)


@router.post("/selfsigned")
def revert_selfsigned(
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    config = _get_config(db)
    try:
        tls_manager.switch_mode("selfsigned")
    except tls_manager.TlsValidationError as exc:
        return templates.TemplateResponse(
            request, "settings/tls.html", {"active": "settings", "current_user": current_user, "config": config, "error": str(exc)}, status_code=400
        )
    config.mode = "selfsigned"
    db.add(config)
    record(db, actor_admin_user_id=current_user.id, action="tls.switch_selfsigned", source_ip=client_ip(request))
    return RedirectResponse("/admin/settings/tls", status_code=303)
