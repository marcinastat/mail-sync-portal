"""Współdzielony obiekt Jinja2Templates z context processorami, które
wstrzykują `branding` i `current_user` do KAŻDEGO renderu panelu — dzięki temu
belka/logo/nazwa są spójne na wszystkich podstronach (wcześniej branding
pojawiał się tylko tam, gdzie router jawnie go przekazał). Wszystkie routery
importują ten jeden obiekt zamiast tworzyć własne instancje."""

from starlette.requests import Request

from fastapi.templating import Jinja2Templates

from .db import session_scope
from .models import AdminUser, BrandingConfig


def _branding_processor(request: Request) -> dict:
    # Krótka sesja tylko do odczytu; błąd (np. brak DB) nie może wywalić
    # renderu — zwracamy None i szablony mają fallback.
    try:
        with session_scope() as db:
            branding = db.query(BrandingConfig).first()
            user = None
            user_id = request.session.get("admin_user_id") if "session" in request.scope else None
            if user_id:
                user = db.get(AdminUser, user_id)
            # odłączamy od sesji, żeby dało się użyć po jej zamknięciu
            db.expunge_all()
            return {"branding": branding, "current_user": user}
    except Exception:
        return {"branding": None, "current_user": None}


templates = Jinja2Templates(
    directory="portal_app/templates",
    context_processors=[_branding_processor],
)


def _fmt_gb(value) -> str:
    try:
        return f"{float(value) / (1024 ** 3):.1f} GB"
    except (TypeError, ValueError):
        return "—"


def _fmt_dt(value, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not value:
        return "—"
    try:
        return value.strftime(fmt)
    except (AttributeError, ValueError):
        return str(value)


def _fmt_mb(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v <= 0:
        return "0 MB"
    if v >= 1024 ** 3:
        return f"{v / (1024 ** 3):.2f} GB"
    return f"{v / (1024 ** 2):.1f} MB"


templates.env.filters["gb"] = _fmt_gb
templates.env.filters["dt"] = _fmt_dt
templates.env.filters["mb"] = _fmt_mb

