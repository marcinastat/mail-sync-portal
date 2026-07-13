# Portal poczty — VM1 (portal) + VM2 (serwer poczty)

Środowisko do archiwizacji/synchronizacji poczty IMAP na dwóch maszynach Rocky Linux 10:

- **VM1 „portal"** — Roundcube, panel administracyjny (`/admin`, aplikacja Python), nginx z TLS offloadingiem, silnik synchronizacji imapsync.
- **VM2 „serwer poczty"** — Postfix + Dovecot (wiele domen wirtualnych), ClamAV, wewnętrzne API do provisioningu wywoływane przez VM1.

Pełny plan projektu: zobacz plik planu w `docs/technical/architecture.md` (kopia zatwierdzonego planu).

## Instalacja

1. Skopiuj `config/install.conf.example` do `config/install.conf` i uzupełnij wartości (podsieć admina, adres IP VM2, itd.).
2. Na VM2: uruchom skrypty z `scripts/vm2/` w kolejności numerycznej (`00-preflight.sh`, `10-base-hardening.sh`, ...).
3. Na VM1: uruchom skrypty z `scripts/vm1/` w kolejności numerycznej.
4. Zaloguj się do `https://<VM1>/admin` i przejdź kreator pierwszego uruchomienia.

Skrypty są idempotentne — ponowne uruchomienie nie powtarza już wykonanych kroków (patrz `scripts/lib/common.sh`).

## Status implementacji

Zobacz `docs/technical/build-status.md` za aktualnym stanem faz z planu.
