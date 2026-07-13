# Monitorowanie synchronizacji

## Pulpit (`/admin/`)

Jeden ekran ze stanem całego środowiska: liczba aktywnych skrzynek, dni do wygaśnięcia certyfikatu TLS, głębokość kolejki zadań (ile oczekuje/trwa/nie powiodło się), łączny "drift" (wiadomości zachowane na serwerze docelowym mimo zniknięcia ze źródła), stan VM2 (health-check, zajętość **obu dysków** — systemowego i pocztowego — osobno, ClamAV), ostatnie zdarzenia audytowe.

## Monitoring dysków VM2

VM2 ma dwa dyski: systemowy i dedykowany na pocztę (`/var/mail/vhosts`). Zajętość obu jest sprawdzana dwutorowo:

- **lokalnie na VM2** co 15 minut (`vm2-disk-check.timer`) — ostrzeżenia trafiają do dziennika systemowego (`journalctl -u vm2-disk-check`), niezależnie od tego, czy VM1 w ogóle żyje;
- **z VM1** co 30 minut (razem z resztą health-checku VM2) — po przekroczeniu progu wysyła alert `disk_low_space` przez skonfigurowane kanały.

Próg ostrzeżenia (domyślnie 85%) ustawia się w `config/install.conf` (`DISK_USAGE_WARNING_PERCENT`).

## Widok skrzynki (`/admin/mailboxes/<id>`)

- Przycisk **"Synchronizuj teraz"** — wymusza natychmiastową synchronizację poza harmonogramem.
- **Historia synchronizacji** — każde uruchomienie z liczbą folderów/wiadomości przesłanych vs. całkowitych, licznikiem "drift" i linkiem do **surowego logu imapsync**.
- Status "w toku" blokuje ponowne uruchomienie, dopóki poprzednie się nie zakończy.

## Throttling (`/admin/settings/throttle`)

Globalne limity: połączeń na minutę/godzinę/dzień oraz liczba równoległych synchronizacji. Kolejka respektuje te limity automatycznie — zadanie, które przekroczyłoby limit, jest po prostu odkładane na później, nie odrzucane.

## Alerty (`/admin/settings/alerts`)

Skonfiguruj kanał e-mail lub webhook i wybierz zdarzenia: nieudana synchronizacja, problem z ClamAV na VM2, zbliżające się wygaśnięcie certyfikatu, niedostępność VM2, naruszenie integralności logu audytowego. Alerty e-mail wymagają uzupełnienia `/etc/portal/alert-smtp.conf` na serwerze (zewnętrzny relay SMTP).

## Eksport (`/admin/reports`, `/admin/audit`)

Status synchronizacji wszystkich skrzynek i pełny log audytowy da się wyeksportować do CSV (dalsza obróbka) lub PDF (gotowy raport).
