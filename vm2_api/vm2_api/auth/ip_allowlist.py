from fastapi import HTTPException, Request, status

from ..config import get_settings

# mTLS na poziomie TLS (uvicorn: ssl_cert_reqs=CERT_REQUIRED + ssl_ca_certs=nasze
# CA) jest właściwą granicą bezpieczeństwa — nasze CA nigdy nie podpisało żadnego
# certyfikatu poza vm1-client, więc samo posiadanie ważnego certyfikatu już
# ogranicza dostęp do VM1. To sprawdzenie IP to dodatkowa warstwa (obrona w
# głąb), niezależna od firewalld na poziomie sieci.
ACTOR_LABEL = "vm1-portal-client"


def require_vm1_ip(request: Request) -> str:
    settings = get_settings()
    client_ip = request.client.host if request.client else None
    if client_ip != settings.allowed_client_ip:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Adres źródłowy nie jest dozwolony dla provisioning API.",
        )
    return ACTOR_LABEL
