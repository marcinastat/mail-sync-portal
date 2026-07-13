# Cykl życia TLS na VM1

Status: placeholder — treść pełna zostanie napisana w Fazie 11/12.

Skrót (patrz `docs/technical/architecture.md` i plan źródłowy):

1. **Domyślnie**: self-signed, ważny 10 lat, generowany przy instalacji (`scripts/vm1/30-nginx.sh`).
2. **certbot (DNS-01)**: jedyny realny tryb automatyczny, bo VM1 nie jest internet-facing — HTTP-01 nie zadziała. Wymaga wyboru dostawcy DNS i uzupełnienia `CERTBOT_DNS_PROVIDER`/`CERTBOT_DNS_CREDENTIALS_FILE` w `config/install.conf`. nginx przełącza się na nowy certyfikat dopiero po potwierdzonym sukcesie certbota (deploy-hook), nigdy wcześniej.
3. **manual paste**: wklejenie certyfikatu + klucza prywatnego przez `/admin`, walidacja (dopasowanie modulusu, ważność, poprawność łańcucha) i self-check HTTPS przed przełączeniem; automatyczny rollback do poprzedniego certyfikatu przy błędzie.

Otwarte: wybór dostawcy DNS dla trybu certbot (patrz `docs/technical/build-status.md` / sekcja "Do doprecyzowania" w planie).
