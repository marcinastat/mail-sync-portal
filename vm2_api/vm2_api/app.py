from fastapi import FastAPI

from .routers import av, domains, health, mailboxes, system

app = FastAPI(
    title="VM2 Provisioning API",
    description="Wewnętrzne API do zarządzania domenami/skrzynkami/AV/aktualizacjami VM2. Dostęp: mTLS + IP allowlist (tylko VM1).",
    docs_url=None,
    redoc_url=None,
)

app.include_router(health.router)
app.include_router(domains.router)
app.include_router(mailboxes.router)
app.include_router(av.router)
app.include_router(system.router)
