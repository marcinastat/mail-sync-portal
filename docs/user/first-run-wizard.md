# Kreator pierwszego uruchomienia

Uruchamia się automatycznie pod `/admin/setup` zaraz po instalacji i blokuje dostęp do reszty panelu, dopóki nie zostanie ukończony.

## Krok 1 — Konto administratora

Login, e-mail, hasło (min. 12 znaków). To pierwsze konto ma rolę `admin`.

## Krok 2 — TOTP (obowiązkowe)

Zeskanuj wyświetlony kod QR aplikacją uwierzytelniającą (Google Authenticator, Aegis, 1Password itp.) i wpisz wygenerowany kod. Po potwierdzeniu zobaczysz **kody odzyskiwania** — zapisz je w bezpiecznym miejscu, każdy działa tylko raz i nie zostaną pokazane ponownie. TOTP jest obowiązkowe dla każdego konta administracyjnego, nie da się go pominąć.

## Krok 3 — Podsieć administracyjna

Wyświetla podsieć skonfigurowaną w `config/install.conf` (`ADMIN_SUBNET_CIDR`), z której firewalld dopuszcza ruch SSH/HTTPS do VM1. Zmiana tej wartości po instalacji wymaga edycji pliku i ponownego uruchomienia `scripts/vm1/80-firewall-rules.sh` na serwerze.

## Krok 4 — Połączenie z VM2

Podaj hostname/IP serwera poczty i port API (domyślnie 8443). System natychmiast testuje połączenie mTLS — jeśli certyfikat kliencki nie został jeszcze skopiowany z VM2 (`ca/vm1-client.*` → `/etc/portal/vm1-client/` na VM1), ten krok się nie powiedzie. Zobacz `INSTALL.md` w repozytorium.

## Krok 5 — Branding

Logo (PNG/JPG) i trzy kolory (główny, tło, akcent). Zostają zastosowane jednocześnie w: panelu administracyjnym, Roundcube (logo) i na stronach błędów nginx (404/429/500) — te ostatnie są w pełni samodzielnymi plikami HTML z logo osadzonym jako base64, więc działają nawet gdyby reszta aplikacji miała problem.

Po tym kroku trafiasz na ekran logowania.
