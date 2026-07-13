# Status implementacji

Odzwierciedla fazy z `docs/technical/architecture.md` / planu źródłowego.

| Faza | Zakres | Status |
|---|---|---|
| 1 | Szkielet repo + biblioteka wspólna skryptów | w trakcie |
| 2 | VM2 warstwa danych (Postgres, Postfix/Dovecot, ClamAV) | nierozpoczęta |
| 3 | VM2 provisioning API | nierozpoczęta |
| 4 | VM1 warstwa bazowa (hardening, Postgres, nginx + TLS) | nierozpoczęta |
| 5 | Roundcube na VM1 | nierozpoczęta |
| 6 | Rdzeń portal_app (auth, schema, wizard, TOTP, systemd-creds) | nierozpoczęta |
| 7 | Domeny/skrzynki/import XLS + auto-provisioning + reset hasła + sync config | nierozpoczęta |
| 8 | Kolejka jobów, worker, scheduler, silnik imapsync, logi/postęp/drift | nierozpoczęta |
| 9 | Hardening bezpieczeństwa | nierozpoczęta |
| 10 | Alerty, dashboard, eksport audytu/raportów | nierozpoczęta |
| 11 | TLS certbot DNS-01 | nierozpoczęta (zablokowana wyborem dostawcy DNS) |
| 12 | Dokumentacja + polish UI | nierozpoczęta |

## Decyzje podjęte podczas implementacji (uzupełniają plan źródłowy)

- **Postfix na VM2 wysyła też pocztę wychodzącą** (rozstrzygnięcie otwartego pytania z planu): dodano usługę `submission` (587, SASL przez Dovecot), firewalld ograniczone do IP VM1 — bez tego Roundcube nie mógłby wysyłać/odpowiadać na pocztę ze zsynchronizowanych skrzynek. Port 25 zostaje jako dodatkowa warstwa (obrona w głąb), również ograniczony do IP VM1.
