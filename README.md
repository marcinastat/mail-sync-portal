# Portal poczty — VM1 (portal) + VM2 (serwer poczty)

Środowisko do archiwizacji/synchronizacji poczty IMAP na dwóch maszynach Rocky Linux 10:

- **VM1 „portal"** — Roundcube, panel administracyjny (`/admin`, aplikacja Python), nginx z TLS offloadingiem, silnik synchronizacji imapsync.
- **VM2 „serwer poczty"** — Postfix + Dovecot (wiele domen wirtualnych), ClamAV, wewnętrzne API do provisioningu wywoływane przez VM1. **Wymaga dwóch dysków**: systemowego i dedykowanego na pocztę (auto-wykrywany, formatowany i montowany pod `/var/mail/vhosts` przez `scripts/vm2/25-mail-disk.sh`).

Pełny plan projektu: zobacz plik planu w `docs/technical/architecture.md` (kopia zatwierdzonego planu).

## Instalacja

Pełna instrukcja krok po kroku dla dwóch czystych VM Rocky Linux 10: **[INSTALL.md](INSTALL.md)**.

Skrót: `config/install.conf` → skrypty `scripts/vm2/00..70` → skopiuj `ca/vm1-client.*` z VM2 na VM1 → skrypty `scripts/vm1/00..90` → `https://<VM1>/admin/setup`.

Skrypty są idempotentne — ponowne uruchomienie nie powtarza już wykonanych kroków (patrz `scripts/lib/common.sh`).

## Status implementacji

Zobacz `docs/technical/build-status.md` za aktualnym stanem faz z planu.
