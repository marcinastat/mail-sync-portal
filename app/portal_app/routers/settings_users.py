import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.hash import argon2
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser
from ..services.audit_service import record

router = APIRouter(prefix="/admin/settings/users", tags=["settings-users"], dependencies=[Depends(require_setup_complete)])
templates = Jinja2Templates(directory="portal_app/templates")


@router.get("")
def list_users(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    users = db.query(AdminUser).order_by(AdminUser.username).all()
    return templates.TemplateResponse(
        request,
        "settings/users.html",
        {"active": "settings", "current_user": current_user, "users": users},
    )


@router.post("")
def create_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    temp_password = secrets.token_urlsafe(16)
    user = AdminUser(username=username, email=email, password_hash=argon2.hash(temp_password), role="admin")
    db.add(user)
    db.flush()
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="admin_user.create",
        target_type="admin_user",
        target_id=str(user.id),
        details={"username": username},
        source_ip=client_ip(request),
    )
    users = db.query(AdminUser).order_by(AdminUser.username).all()
    return templates.TemplateResponse(
        request,
        "settings/users.html",
        {
            "active": "settings",
            "current_user": current_user,
            "users": users,
            "new_user_temp_password": temp_password,
            "new_user_username": username,
        },
    )


@router.post("/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    user = db.get(AdminUser, user_id)
    if user and user.id != current_user.id:
        user.is_active = False
        db.add(user)
        record(
            db,
            actor_admin_user_id=current_user.id,
            action="admin_user.deactivate",
            target_type="admin_user",
            target_id=str(user.id),
            source_ip=client_ip(request),
        )
    return RedirectResponse("/admin/settings/users", status_code=303)
