# Status implementacji

Wszystkie fazy z planu źródłowego zaimplementowane.

| Faza | Zakres | Status |
|---|---|---|
| 1 | Szkielet repo + biblioteka wspólna skryptów | gotowe |
| 2 | VM2 warstwa danych (Postgres, Postfix/Dovecot, ClamAV) | gotowe |
| 3 | VM2 provisioning API | gotowe |
| 4 | VM1 warstwa bazowa (hardening, Postgres, nginx + TLS) | gotowe |
| 5 | Roundcube na VM1 | gotowe |
| 6 | Rdzeń portal_app (auth, schema, wizard, TOTP, systemd-creds) | gotowe |
| 7 | Domeny/skrzynki/import XLS + auto-provisioning + reset hasła + sync config | gotowe |
| 8 | Kolejka jobów, worker, scheduler, silnik imapsync, logi/postęp/drift | gotowe |
| 9 | Hardening bezpieczeństwa | gotowe |
| 10 | Alerty, dashboard, eksport audytu/raportów | gotowe |
| 11 | TLS certbot DNS-01 | gotowe (opcjonalny skrypt, nie część stałej sekwencji) |
| 12 | Dokumentacja + polish UI | gotowe |

## Decyzje podjęte podczas implementacji (uzupełniają plan źródłowy)

- **Postfix na VM2 wysyła też pocztę wychodzącą** (rozstrzygnięcie otwartego pytania z planu): dodano usługę `submission` (587, SASL przez Dovecot), firewalld ograniczone do IP VM1 — bez tego Roundcube nie mógłby wysyłać/odpowiadać na pocztę ze zsynchronizowanych skrzynek. Port 25 zostaje jako dodatkowa warstwa (obrona w głąb), również ograniczony do IP VM1.
- **Hasło skrzynki docelowej przechowywane jawnie zaszyfrowane** (`mailboxes.destination_password_encrypted`) — niezbędne, żeby imapsync mógł się logować na VM2 po ręcznym resecie hasła (samo hasło nigdy nie trafia do audit logu).
- **Eksport PDF** przez `reportlab` (serwerowo generowany plik do pobrania), nie "print to PDF" w przeglądarce.
- **Alerty e-mail** wymagają ręcznej konfiguracji zewnętrznego relaya SMTP (`/etc/portal/alert-smtp.conf`) — VM1 celowo nie ma własnego MTA.
- **VM2 wymaga dwóch dysków** (systemowy + dedykowany na pocztę). `scripts/vm2/25-mail-disk.sh` autodetekuje dysk inny niż systemowy, formatuje go (XFS) TYLKO jeśli jest zupełnie pusty, dodaje wpis do `/etc/fstab` przez UUID i montuje pod `/var/mail/vhosts`. Ambiguity (0 lub >1 kandydatów) kończy się twardym błędem, nie zgadywaniem — override przez `VM2_MAIL_DISK` w `install.conf`. Oba dyski monitorowane lokalnie (`vm2-disk-check.timer`, co 15 min, próg `DISK_USAGE_WARNING_PERCENT`) i zdalnie z VM1 (`portal-environment-check.timer` → alert `disk_low_space`).
- **Ręczne dodawanie pojedynczej skrzynki** (`/admin/mailboxes/new`) — alternatywa dla importu XLS/CSV, współdzieli logikę provisioningu (`services/import_service.upsert_mailbox`).
- **Wdrożenie VM1 → VM2 przez SSH** (`scripts/vm1/sync-to-vm2.sh` + `scripts/vm1/fetch-vm2-client-cert.sh`) — generuje klucz SSH na VM1, wypycha go na VM2 (hasło roota podawane jednorazowo), synchronizuje repo przez rsync i pobiera z powrotem certyfikat kliencki mTLS. Skrypty `scripts/vm2/*.sh` nadal uruchamia się ręcznie i po kolei bezpośrednio na VM2 — świadomie, żeby nie wykonywać zdalnie kroków wymagających decyzji operatora (np. wybór dysku pocztowego przy niejednoznaczności).
- **Poprawki po pierwszym realnym teście na czystym Rocky Linux 10 Minimal**: (1) `scripts/vm2/50-provisioning-api.sh` nie generował faktycznie certyfikatu klienckiego dla VM1 mimo komunikatu w logu — naprawione (brakujące wywołanie `mtls_setup_vm1_client`); (2) ClamAV/freshclam nie mógł zapisać baz w `/var/lib/clamav` z powodu niedopasowania właściciela katalogu (pakiet EPEL zakłada `clamupdate`, nasza konfiguracja świadomie używa `clamscan` wszędzie) — naprawione jawnym `chown`; (3) Rocky Linux "Minimal" nie ma domyślnie `openssl`/`rsync`/`tar`/`nano` — dodano `install_base_prereqs()` w `common.sh`, wołane z obu `00-preflight.sh`.
- **Import obsługuje też CSV** (obok XLSX/XLS), z auto-wykrywaniem separatora (`,`/`;`/tab). Szablony do pobrania z `/admin/imports` (`template.csv`, `template.xlsx`), pełny opis schematu w `docs/user/importing-mailboxes.md` i bezpośrednio na stronie importu.

## Znane uproszczenia / dalsze kroki

- Dokładny schemat kolumn XLS dopasowuje popularne warianty nazw (PL/EN); jeśli dostawca danych używa innych nagłówków, rozszerz `_HEADER_ALIASES` w `app/portal_app/services/xls_parser.py`.
- Wskaźnik "drift" to heurystyka (spadek `messages_total` względem ostatniego udanego przebiegu), nie porównanie zbiorów UID.
- Backup/DR świadomie poza zakresem repo (snapshoty po stronie hypervisora) — patrz `docs/technical/backup-strategy.md`.
- Rola `operator` (read-only) ma już miejsce w schemacie (`admin_users.role`), ale UI/autoryzacja rozróżnia na razie tylko `admin`.
