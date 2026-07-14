from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, ImapsyncConfig
from ..services import imapsync_flags
from ..services.audit_service import record
from ..templating import templates

router = APIRouter(
    prefix="/admin/settings/imapsync",
    tags=["settings-imapsync"],
    dependencies=[Depends(require_setup_complete)],
)

# Lista pokazywana w UI jako podpowiedź, co wolno wpisać w polu custom.
ALLOWED_HINT = sorted(imapsync_flags._ALLOWED_FLAGS.keys())


def _get_or_create(db: Session) -> ImapsyncConfig:
    cfg = db.query(ImapsyncConfig).first()
    if cfg is None:
        cfg = ImapsyncConfig()
        db.add(cfg)
        db.flush()
    return cfg


@router.get("")
def imapsync_page(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    cfg = _get_or_create(db)
    return templates.TemplateResponse(
        request,
        "settings/imapsync.html",
        {"active": "settings", "current_user": current_user, "cfg": cfg,
         "allowed": ALLOWED_HINT, "saved": request.query_params.get("saved"), "error": None},
    )


@router.post("")
def save_imapsync(
    request: Request,
    verify_source_ssl: bool = Form(False),
    add_missing_headers: bool = Form(False),
    allow_size_mismatch: bool = Form(False),
    max_size_mb: int = Form(0),
    timeout_seconds: int = Form(0),
    custom_flags: str = Form(""),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    cfg = _get_or_create(db)
    # Walidacja pola custom allowlistą — przy błędzie NIE zapisujemy.
    try:
        imapsync_flags.validate_custom_flags(custom_flags)
    except imapsync_flags.ImapsyncFlagError as exc:
        return templates.TemplateResponse(
            request,
            "settings/imapsync.html",
            {"active": "settings", "current_user": current_user, "cfg": cfg,
             "allowed": ALLOWED_HINT, "saved": None, "error": str(exc)},
            status_code=400,
        )

    cfg.verify_source_ssl = verify_source_ssl
    cfg.add_missing_headers = add_missing_headers
    cfg.allow_size_mismatch = allow_size_mismatch
    cfg.max_size_mb = max(0, max_size_mb)
    cfg.timeout_seconds = max(0, timeout_seconds)
    cfg.custom_flags = custom_flags.strip()
    db.add(cfg)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="imapsync_config.update",
        target_type="imapsync_config",
        target_id=str(cfg.id),
        details={"verify_source_ssl": verify_source_ssl, "add_missing_headers": add_missing_headers,
                 "max_size_mb": cfg.max_size_mb, "timeout_seconds": cfg.timeout_seconds,
                 "allow_size_mismatch": allow_size_mismatch, "custom_flags": cfg.custom_flags},
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/settings/imapsync?saved=1", status_code=303)
