# Schemat baz danych

## VM1 — `portal_db` (SQLAlchemy modele w `app/portal_app/models/`, migracja `app/portal_app/migrations/versions/0001_initial.py`)

| Tabela | Rola |
|---|---|
| `admin_users`, `totp_credentials` | konta panelu, TOTP obowiązkowe |
| `domains` | domena źródłowa/docelowa + hostname/port serwera IMAP źródła |
| `credentials` | poświadczenia źródłowe (hasło szyfrowane), `auth_type` gotowe pod OAuth2 |
| `mailboxes` | skrzynka docelowa, `vm2_mailbox_id`, `password_override`, `destination_password_encrypted` |
| `sync_jobs` | konfiguracja synchronizacji per skrzynka (days_back, delete_on_dest...) |
| `job_queue`, `job_runs` | kolejka zadań (SKIP LOCKED) i historia uruchomień |
| `import_batches`, `import_rows` | historia importów XLS z deduplikacją (`match_type`) |
| `throttle_policies` | globalne limity połączeń/współbieżności |
| `audit_log` | append-only, hash-chaining (`row_hash = SHA256(prev_hash || dane)`) |
| `branding_config`, `tls_config`, `instance_state`, `vm2_connection`, `alert_channels` | konfiguracja środowiska |

Sekrety (hasła źródłowe, `destination_password_encrypted`) szyfrowane Fernetem kluczem dostarczanym przez `systemd-creds` (`portal_app/config.py`, `services/credential_crypto.py`) — nigdy plaintext w bazie ani na dysku.

## VM1 — `roundcube_db`

Standardowy schemat Roundcube (`SQL/postgres.initial.sql` z paczki Roundcube), osobna rola `roundcube_app`.

## VM2 — `mail_db` (`sql/vm2/001_schema.sql`, `002_grants.sql`)

| Tabela | Rola |
|---|---|
| `virtual_domains` | domeny wirtualne obsługiwane przez Postfix/Dovecot |
| `virtual_mailboxes` | skrzynki, hasło w formacie SHA512-CRYPT (Dovecot), `password_overridden` |
| `audit_log` | append-only, hash-chaining — mirror wzorca z VM1, dla wywołań provisioning API |

Rola aplikacyjna `mail_app` ma `REVOKE UPDATE, DELETE` na `audit_log` — nawet kod appki nie może modyfikować historii, tylko dopisywać.
