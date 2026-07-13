# Architektura: Portal (VM1) + Serwer Poczty (VM2)

> Ten dokument jest kopią zatwierdzonego planu projektu (`C:\Users\Marcin\.claude\plans\planujemy-2-vm-rockylinux-linked-grove.md`). Aktualizuj oba pliki równolegle, jeśli architektura się zmienia.

## Kontekst

Dwuwarstwowe środowisko do archiwizacji/synchronizacji poczty IMAP: aplikacja na VM1 („portal") pobiera poświadczenia skrzynek z pliku XLS (dostarczonego w zaszyfrowanym archiwum), automatycznie zakłada odpowiadające skrzynki na VM2 („serwer poczty") i utrzymuje jednokierunkową, nigdy-nie-niszczącą synchronizację ze źródłowym serwerem IMAP za pomocą imapsync. VM1 udostępnia też Roundcube (webmail) i panel administracyjny do zarządzania całością.

Kluczowe ustalenia:
- Provisioning: zwykłe skrypty bash (nie Ansible/Terraform), sterowane jednym plikiem konfiguracyjnym.
- VM1 jest tylko wewnętrzna (VPN/LAN), nie wystawiona do internetu — certbot tylko w trybie DNS-01.
- Skala: mała, do ~50 skrzynek — bez Redis/Celery, bez HA/shardingu.
- Panel `/admin`: lokalne konta + wymuszone TOTP 2FA.
- VM1 ma wychodzący dostęp do internetu (PGDG, nginx.org, PyPI, EPEL).
- Backup/DR poza zakresem repo — snapshoty po stronie hypervisora.
- Hasło skrzynki docelowej na VM2 = lustrzane odwzorowanie hasła źródłowego z XLS.
- Auth źródłowych serwerów IMAP: fundament pod hasła, schemat rozszerzalny o OAuth2.

## Architektura i granice zaufania

```
[Podsieć admin/VPN]
   |  HTTPS 443 (nginx TLS offload)     SSH 22 (tylko z tej podsieci)
   v
VM1 "portal" (mała)
  nginx.org nginx — terminacja TLS
    /        -> Roundcube (php-fpm)
    /admin   -> Gunicorn (portal_app)
    błędy    -> branded 404/429/500
  PostgreSQL 17: roundcube_db + portal_db (jedna instancja, role per-DB)
  portal-worker.service + portal-scheduler.timer (kolejka jobów w Postgresie)
  imapsync (subprocess, wywoływany tylko z bezpieczną allowlistą flag)
  fail2ban: sshd, admin-auth, roundcube-auth, nginx-limit-req
  firewalld: 22/443 tylko z podsieci admin; wychodzące do VM2 + zewn. IMAP + repo
   |                                    |
   | wychodzące IMAP/993 do             | wychodzące HTTPS/mTLS do
   | zewnętrznych serwerów źródłowych   | VM2 provisioning API :8443
   v                                    v
[Zewnętrzne serwery IMAP źródłowe,   VM2 "serwer poczty" (większa), tylko z IP VM1
 wiele domen/tenantów]                 Postfix (virtual domains) + Dovecot + ClamAV milter
                                        PostgreSQL 17: mail_db
                                        provisioning-api.service (FastAPI, mTLS, :8443)
                                        firewalld: 143/993 + 8443 tylko z IP VM1
```

VM2 nigdy nie jest osiągalna bezpośrednio z podsieci admin — jedynym punktem dostępu do danych pocztowych jest VM1 (Roundcube + silnik synchronizacji).

## Layout repozytorium

```
config/install.conf.example
scripts/lib/{common.sh,checks.sh,mtls.sh}
scripts/vm1/00..90-*.sh
scripts/vm2/00..70-*.sh
templates/{nginx,dovecot,postfix,roundcube,systemd}/*.tmpl
app/portal_app/          # aplikacja /admin: FastAPI + Jinja2/HTMX na Gunicornie
vm2_api/                 # serwis API na VM2 (FastAPI, mTLS)
docs/technical/*.md
docs/user/*.md
ca/                      # generowane lokalnie przy instalacji, NIGDY nie commitowane
```

## Kluczowe decyzje techniczne

| Obszar | Wybór | Uzasadnienie |
|---|---|---|
| Framework aplikacji | FastAPI + Jinja2 + HTMX/Alpine, Gunicorn+UvicornWorker | nowoczesny UI bez node build pipeline |
| Kolejka zadań | Tabela `job_queue` w Postgresie, `SELECT...FOR UPDATE SKIP LOCKED`, worker jako systemd service + scheduler jako timer co minutę | przy ~50 skrzynkach Redis+Celery to zbędna złożoność |
| Bezpieczeństwo imapsync | Budowniczy argv z twardą allowlistą flag; flagi niszczące źródło nie istnieją w kodzie | wymóg nienaruszalności źródła wymuszony na poziomie kodu |
| Antywirus VM2 | ClamAV (clamd + clamav-milter + clamdscan on-demand) | jedyny poważny FOSS AV dla Linuksa/poczty |
| Archiwa (XLS import) | ZIP (pyzipper) i 7z (py7zr) w pełni wspierane; RAR best-effort przez systemowy `unrar` | RAR wymaga niewolnej binarki — nie bundlujemy |
| Hasło skrzynki docelowej VM2 | Lustrzane odwzorowanie hasła źródłowego z XLS | decyzja użytkownika, prostsze |
| TLS na VM1 | Self-signed 10 lat domyślnie; certbot tylko DNS-01; manual paste z walidacją | VM1 nie jest internet-facing |

Pełne szczegóły w dedykowanych dokumentach:

- Sieć i granice zaufania: `docs/technical/network.md`
- Schemat baz danych: `docs/technical/database-schema.md`
- Cykl życia TLS: `docs/technical/tls-lifecycle.md`
- Backup/DR: `docs/technical/backup-strategy.md`
- Runbook po `dnf update`: `docs/technical/runbooks/post-update-checklist.md`
- Status implementacji per faza: `docs/technical/build-status.md`
- Instalacja krok po kroku: `INSTALL.md` (root repo)
- Dokumentacja użytkowa: `docs/user/` (dostępna też w panelu pod `/admin/docs`)
