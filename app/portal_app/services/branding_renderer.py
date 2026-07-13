import base64
import io
import logging
import mimetypes
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from PIL import Image

from ..models import BrandingConfig

logger = logging.getLogger("portal.branding")

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "branding"
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_STAGE_DIR = Path("/var/lib/portal-app/branding-stage")

_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

_ERROR_PAGES = {
    "404": ("Nie znaleziono", "Strona nie została znaleziona."),
    "429": ("Zbyt wiele prób", "Zbyt wiele prób logowania. Spróbuj ponownie za chwilę."),
    "500": ("Błąd serwera", "Wystąpił błąd serwera. Spróbuj ponownie później."),
}


def _logo_data_uri(logo_path: str | None) -> str | None:
    if not logo_path:
        return None
    full_path = _STATIC_DIR / "branding" / logo_path
    if not full_path.exists():
        return None
    mime, _ = mimetypes.guess_type(full_path.name)
    encoded = base64.b64encode(full_path.read_bytes()).decode("ascii")
    return f"data:{mime or 'image/png'};base64,{encoded}"


def save_logo(upload_bytes: bytes) -> str:
    """Zawsze zapisuje jako logo.png pod stałą ścieżką — Roundcube (Faza 5,
    config.inc.php: skin_logo) i strony błędów nginx odwołują się do niej
    raz, na stałe, więc nie trzeba ich ponownie renderować przy zmianie logo."""
    branding_dir = _STATIC_DIR / "branding"
    branding_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(io.BytesIO(upload_bytes))
    image.thumbnail((512, 512))
    image.convert("RGBA").save(branding_dir / "logo.png", format="PNG")
    return "logo.png"


def render_all(branding: BrandingConfig) -> None:
    """Jeden render zasila jednocześnie: tokens.css panelu admina (bezpośredni
    zapis, portal-app jest właścicielem własnego static/), oraz statyczne
    strony błędów nginx (przez staging + wąski sudo helper, bo /var/www/errors
    należy do roota — patrz bin/apply-branding.sh)."""
    logo_uri = _logo_data_uri(branding.logo_path)

    tokens_css = (
        ":root {\n"
        f"  --brand-primary: {branding.primary_color};\n"
        f"  --brand-secondary: {branding.secondary_color};\n"
        f"  --brand-accent: {branding.accent_color};\n"
        "}\n"
    )
    (_STATIC_DIR / "css" / "tokens.css").write_text(tokens_css, encoding="utf-8")

    _STAGE_DIR.mkdir(parents=True, exist_ok=True)
    template = _env.get_template("error_page.html.j2")
    for code, (title, message) in _ERROR_PAGES.items():
        html = template.render(
            code=code,
            title=title,
            message=message,
            logo_data_uri=logo_uri,
            primary_color=branding.primary_color,
            secondary_color=branding.secondary_color,
            accent_color=branding.accent_color,
        )
        (_STAGE_DIR / f"{code}.html").write_text(html, encoding="utf-8")

    # Include konfiguracji Roundcube (product_name + logo). Logo jako data: URI
    # — Roundcube używa go dosłownie, bez przepisywania ścieżki przez static.php
    # (ścieżki względne/absolutne skin_logo są zawodne: albo 404, albo błędny
    # prefiks skins/elastic). apply-branding.sh (root) instaluje ten plik do
    # /etc/portal/roundcube-branding.php, a config.inc.php go include'uje.
    product_name = (branding.product_name or "Portal Poczty").replace("'", "\\'")
    rc_lines = ["<?php", f"$config['product_name'] = '{product_name}';"]
    if logo_uri:
        rc_lines.append(f"$config['skin_logo'] = '{logo_uri}';")
    (_STAGE_DIR / "roundcube-branding.php").write_text("\n".join(rc_lines) + "\n", encoding="utf-8")

    # Zastosowanie brandingu do stron błędów nginx (przez sudo helper) jest
    # NAJMNIEJ krytyczną częścią — tokens.css (motyw panelu) i logo są już
    # zapisane wyżej. Błąd tego kroku nie może wywalać całego kreatora
    # (obserwowane: 500 na kroku brandingu), więc jest best-effort: logujemy
    # ostrzeżenie zamiast rzucać wyjątek. Strony błędów można odświeżyć
    # później ponowną zmianą brandingu.
    try:
        result = subprocess.run(
            ["/usr/bin/sudo", "-n", "/opt/portal-app/bin/apply-branding.sh"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("apply-branding.sh nie powiodło się (branding stron błędów nginx pominięty): %s", result.stderr.strip())
    except Exception as exc:
        logger.warning("Nie udało się uruchomić apply-branding.sh (branding stron błędów nginx pominięty): %s", exc)
