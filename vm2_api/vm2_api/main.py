import ssl

import uvicorn

from .config import get_settings


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "vm2_api.app:app",
        host="0.0.0.0",
        port=settings.listen_port,
        ssl_certfile=str(settings.tls_cert),
        ssl_keyfile=str(settings.tls_key),
        ssl_ca_certs=str(settings.tls_ca),
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        workers=1,  # stan tokenu reboot w pamięci procesu wymaga dokładnie 1 workera
        log_level="info",
    )


if __name__ == "__main__":
    run()
