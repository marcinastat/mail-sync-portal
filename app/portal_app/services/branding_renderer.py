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

# (tytuł, krótki komunikat, wyjaśnienie „co się dzieje / co zrobić")
_ERROR_PAGES = {
    "403": (
        "Brak dostępu",
        "Nie masz uprawnień do tej strony.",
        "Ta sekcja wymaga zalogowania lub wyższych uprawnień. Jeśli sądzisz, że to pomyłka, "
        "zaloguj się ponownie albo skontaktuj się z administratorem portalu.",
    ),
    "404": (
        "Nie znaleziono",
        "Ta strona nie istnieje.",
        "Adres jest błędny lub zasób został przeniesiony. Sprawdź link albo wróć do panelu i "
        "przejdź do właściwej sekcji z menu.",
    ),
    "429": (
        "Zbyt wiele prób",
        "Chwilowo zablokowano dalsze próby.",
        "Wykryliśmy zbyt wiele żądań w krótkim czasie (ochrona przed atakami na logowanie). "
        "Odczekaj minutę i spróbuj ponownie. Przy uporczywych próbach adres może zostać "
        "czasowo zablokowany przez fail2ban.",
    ),
    "500": (
        "Błąd serwera",
        "Coś poszło nie tak po naszej stronie.",
        "To nie jest problem z Twoimi danymi — wystąpił nieoczekiwany błąd aplikacji. Spróbuj "
        "ponownie za chwilę. Jeśli błąd się powtarza, przekaż administratorowi przybliżony czas "
        "zdarzenia — szczegóły są w logach portalu.",
    ),
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


# Trwała kopia logo POZA drzewem aplikacji (/opt jest celem rsync --delete przy
# każdym deployu — patrz scripts/vm1/50-portal-app.sh). Dzięki niej logo panelu
# jest samonaprawialne: nawet gdy deploy skasuje static/branding, przy starcie
# usługi odtwarzamy je ze stagingu (ensure_panel_logo). /var/lib/portal-app jest
# w ReadWritePaths i nie jest ruszane przez rsync kodu.
_STAGE_LOGO = _STAGE_DIR / "logo.png"


def save_logo(upload_bytes: bytes) -> str:
    """Zawsze zapisuje jako logo.png pod stałą ścieżką — Roundcube (Faza 5,
    config.inc.php: skin_logo) i strony błędów nginx odwołują się do niej
    raz, na stałe, więc nie trzeba ich ponownie renderować przy zmianie logo."""
    branding_dir = _STATIC_DIR / "branding"
    branding_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(io.BytesIO(upload_bytes))
    image.thumbnail((512, 512))
    image.convert("RGBA").save(branding_dir / "logo.png", format="PNG")
    # Trwała kopia poza /opt — źródło samonaprawy po deployu (patrz wyżej).
    _STAGE_DIR.mkdir(parents=True, exist_ok=True)
    image.convert("RGBA").save(_STAGE_LOGO, format="PNG")
    # Favicon prosto z wgranego logo — portal sam przeskalowuje (można wgrać
    # logo w dowolnej, także większej rozdzielczości). Zapisujemy do static/
    # (serwowane) i do stagingu (samonaprawa po deployu, jak logo.png).
    _generate_favicons(upload_bytes, branding_dir)
    return "logo.png"


_FAVICON_PNGS = [(32, "favicon-32.png"), (180, "apple-touch-icon.png")]


def _generate_favicons(upload_bytes: bytes, branding_dir) -> None:
    """Tworzy favicon.ico (16+32) i apple-touch-icon (180) ze skalowania logo.
    Best-effort — brak favicona nie może wywalić zapisu brandingu."""
    try:
        for size, name in _FAVICON_PNGS:
            ico = Image.open(io.BytesIO(upload_bytes)).convert("RGBA")
            ico.thumbnail((size, size))
            ico.save(branding_dir / name, format="PNG")
            ico.save(_STAGE_DIR / name, format="PNG")
        # Klasyczny favicon.ico z osadzonymi rozmiarami 16 i 32 (kompatybilność).
        base = Image.open(io.BytesIO(upload_bytes)).convert("RGBA")
        base.save(branding_dir / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32)])
        base.save(_STAGE_DIR / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32)])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Nie udało się wygenerować favicona z logo: %s", exc)


def ensure_panel_logo() -> None:
    """Samonaprawa logo panelu: jeśli static/branding/logo.png zniknęło (np.
    skasowane przez rsync --delete przy deployu), a mamy trwałą kopię w stagingu,
    odtwarzamy je. Wołane przy starcie aplikacji (app.py). Best-effort — brak
    logo nie może wywalić startu usługi."""
    try:
        branding_dir = _STATIC_DIR / "branding"
        panel_logo = branding_dir / "logo.png"
        if panel_logo.exists() or not _STAGE_LOGO.exists():
            return
        branding_dir.mkdir(parents=True, exist_ok=True)
        # Odtwórz logo ORAZ favicony z trwałej kopii (te same pliki co save_logo).
        for name in ["logo.png", "favicon.ico", "favicon-32.png", "apple-touch-icon.png"]:
            src = _STAGE_DIR / name
            if src.exists():
                (branding_dir / name).write_bytes(src.read_bytes())
        logger.info("Odtworzono logo/favicony panelu ze stagingu po deployu.")
    except Exception as exc:  # noqa: BLE001 — logo to nie funkcja krytyczna
        logger.warning("Nie udało się odtworzyć logo panelu ze stagingu: %s", exc)


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
    for code, (title, message, explanation) in _ERROR_PAGES.items():
        html = template.render(
            code=code,
            title=title,
            message=message,
            explanation=explanation,
            product_name=branding.product_name or "Portal Poczty",
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
