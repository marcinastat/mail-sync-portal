from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, NetworkAccessConfig
from ..services import network_access
from ..services.audit_service import record
from ..templating import templates

router = APIRouter(
    prefix="/admin/settings/network",
    tags=["settings-network"],
    dependencies=[Depends(require_setup_complete)],
)


def _get_or_create(db: Session) -> NetworkAccessConfig:
    cfg = db.query(NetworkAccessConfig).first()
    if cfg is None:
        cfg = NetworkAccessConfig(admin_networks="", webmail_networks="")
        db.add(cfg)
        db.flush()
    return cfg


@router.get("")
def network_page(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    cfg = _get_or_create(db)
    return templates.TemplateResponse(
        request,
        "settings/network.html",
        {"active": "settings", "current_user": current_user, "cfg": cfg,
         "saved": request.query_params.get("saved"), "error": None},
    )


@router.post("")
def save_network(
    request: Request,
    admin_networks: str = Form(""),
    webmail_networks: str = Form(""),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    cfg = _get_or_create(db)

    admin_valid, admin_bad = network_access.parse_cidrs(admin_networks)
    web_valid, web_bad = network_access.parse_cidrs(webmail_networks)
    if admin_bad or web_bad:
        return templates.TemplateResponse(
            request,
            "settings/network.html",
            {"active": "settings", "current_user": current_user, "cfg": cfg, "saved": None,
             "error": "Niepoprawne wpisy (oczekiwano adresów/CIDR, np. 192.168.88.0/24): "
                      + ", ".join(admin_bad + web_bad)},
            status_code=400,
        )

    # Najpierw wypchnij do nginx (z rollbackiem po stronie helpera). Dopiero gdy
    # nginx zaakceptuje — zapisz w bazie jako obowiązujące. Kolejność chroni przed
    # stanem "w bazie jest, ale nginx tego nie przyjął".
    try:
        network_access.render_and_apply(admin_valid, web_valid)
    except RuntimeError as exc:
        return templates.TemplateResponse(
            request,
            "settings/network.html",
            {"active": "settings", "current_user": current_user, "cfg": cfg, "saved": None, "error": str(exc)},
            status_code=400,
        )

    cfg.admin_networks = "\n".join(admin_valid)
    cfg.webmail_networks = "\n".join(web_valid)
    cfg.applied_at = datetime.now(timezone.utc)
    db.add(cfg)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="network_access.update",
        target_type="network_access_config",
        target_id=str(cfg.id),
        details={"admin_networks": admin_valid, "webmail_networks": web_valid},
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/settings/network?saved=1", status_code=303)
