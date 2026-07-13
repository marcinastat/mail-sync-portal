# Branding i wygląd

Logo i kolory ustawia się raz w kreatorze pierwszego uruchomienia. Aktualnie edycja po instalacji odbywa się przez ponowne wypełnienie kroku 5 kreatora (pełny ekran ustawień brandingu poza kreatorem to możliwe rozszerzenie na przyszłość).

## Co się zmienia razem

Jeden zapis brandingu aktualizuje jednocześnie:

- kolory (`--brand-primary`, `--brand-secondary`, `--brand-accent`) w panelu administracyjnym,
- logo w Roundcube (stały adres `/admin/static/branding/logo.png` — Roundcube nie wymaga ponownej konfiguracji przy zmianie logo),
- statyczne strony błędów nginx (404/429/500) — samodzielne pliki HTML z logo osadzonym jako base64, więc renderują się nawet przy awarii reszty aplikacji.

## Dlaczego logo zawsze zapisuje się jako `logo.png`

Niezależnie od formatu wgranego pliku (PNG/JPG), system konwertuje go i zapisuje pod stałą nazwą. Dzięki temu Roundcube i strony błędów nginx nie muszą być ponownie renderowane przy każdej zmianie logo — wystarczy podmienić plik.
