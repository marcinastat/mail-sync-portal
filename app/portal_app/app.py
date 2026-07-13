from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .routers import (
    audit,
    auth,
    dashboard,
    docs,
    domains,
    imports,
    mailboxes,
    reports,
    settings_alerts,
    settings_index,
    settings_throttle,
    settings_tls,
    settings_users,
    setup_wizard,
)

settings = get_settings()

app = FastAPI(title="Portal Poczty — Panel administracyjny", docs_url=None, redoc_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="portal_session",
    same_site="lax",
    https_only=True,
    max_age=60 * 60 * 8,
)

app.mount("/admin/static", StaticFiles(directory="portal_app/static"), name="static")

app.include_router(setup_wizard.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(domains.router)
app.include_router(mailboxes.router)
app.include_router(imports.router)
app.include_router(audit.router)
app.include_router(reports.router)
app.include_router(docs.router)
app.include_router(settings_index.router)
app.include_router(settings_throttle.router)
app.include_router(settings_alerts.router)
app.include_router(settings_tls.router)
app.include_router(settings_users.router)
