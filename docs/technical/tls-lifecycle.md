# Cykl życia TLS na VM1

Status: placeholder — treść pełna zostanie napisana w Fazie 11/12.

Skrót (patrz `docs/technical/architecture.md` i plan źródłowy):

1. **Domyślnie**: self-signed, ważny 10 lat, generowany przy instalacji (`scripts/vm1/30-nginx.sh`).
2. **certbot (DNS-01)**: jedyny realny tryb automatyczny, bo VM1 nie jest internet-facing — HTTP-01 nie zadziała. Wymaga wyboru dostawcy DNS i uzupełnienia `CERTBOT_DNS_PROVIDER`/`CERTBOT_DNS_CREDENTIALS_FILE` w `config/install.conf`. nginx przełącza się na nowy certyfikat dopiero po potwierdzonym sukcesie certbota (deploy-hook), nigdy wcześniej.
3. **manual paste**: wklejenie certyfikatu + klucza prywatnego przez `/admin`, walidacja (dopasowanie modulusu, ważność, poprawność łańcucha) i self-check HTTPS przed przełączeniem; automatyczny rollback do poprzedniego certyfikatu przy błędzie.

## Jak to jest zaimplementowane

- `/etc/portal/tls/active/{fullchain.pem,privkey.pem}` to zawsze symlinki do jednego z: `selfsigned/`, `manual/`, `certbot/`. nginx zawsze czyta z `active/` — przełączanie trybu to tylko podmiana celu symlinka, nigdy edycja konfiguracji nginx.
- Przełączanie wykonuje `/opt/portal-app/bin/apply-tls.sh <tryb>`, uruchamiany przez `portal-app` wyłącznie przez wąski `sudoers.d` (bo `/etc/portal/tls` należy do roota). Skrypt zawsze robi `nginx -t` po przełączeniu; jeśli się nie powiedzie, przywraca poprzedni cel symlinka.
- **manual**: `/admin/settings/tls` — wklejenie certyfikatu+klucza, walidacja (`portal_app/services/tls_manager.py`: dopasowanie klucza do certyfikatu, sprawdzenie ważności) przed przełączeniem.
- **certbot (DNS-01)**: `scripts/vm1/certbot-setup.sh` (uruchamiany ręcznie na serwerze, nie przez UI — wymaga poświadczeń API dostawcy DNS w pliku wskazanym przez `CERTBOT_DNS_CREDENTIALS_FILE` w `install.conf`). Deploy-hook certbota (`templates/certbot/deploy-hook.sh.tmpl`) kopiuje nowy certyfikat do `certbot/` i przełącza `active/` dopiero po potwierdzonym sukcesie wydania/odnowienia.

Otwarte: konkretny wybór dostawcy DNS (Cloudflare/Route53/inny) zależy od tego, gdzie faktycznie jest hostowana strefa DNS domeny VM1 — ustaw `CERTBOT_DNS_PROVIDER` w `install.conf` na nazwę wtyczki certbota (`python3-certbot-dns-<provider>`).
