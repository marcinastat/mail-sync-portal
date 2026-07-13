# Backup / DR

Status: **poza zakresem tego repozytorium** (decyzja użytkownika) — zakładamy, że całe VM1 i VM2 są objęte snapshotami na poziomie hypervisora.

Wskazówki dla spójnych snapshotów / backupów zewnętrznych, jeśli mimo wszystko będą kiedyś potrzebne:

- **VM1**: `portal_db` (Postgres — konfiguracja, audit log, historia importów/synchronizacji), `roundcube_db`, `/etc/portal/secrets/` (jeśli nie zarządzane przez `systemd-creds`), logi imapsync pod `job_runs.imapsync_log_path`.
- **VM2**: `mail_db` (Postgres — domeny/skrzynki wirtualne), maildiry Dovecota, definicje ClamAV (opcjonalnie, łatwe do odtworzenia przez `freshclam`).
- Backup bazy danych w locie: `pg_dump`/`pg_basebackup` per instancja; snapshot na poziomie woluminu powinien objąć Postgres i maildiry w tym samym momencie spójności, jeśli nie korzysta się z narzędzi bazodanowych.
- Audit log jest append-only z hash-chainingiem — kopia zapasowa powinna obejmować całą tabelę, żeby zachować możliwość weryfikacji integralności po odtworzeniu.
