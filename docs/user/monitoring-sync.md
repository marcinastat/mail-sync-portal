# Monitorowanie synchronizacji

## Pulpit (`/admin/`)

Jeden ekran ze stanem całego środowiska: liczba aktywnych skrzynek, dni do wygaśnięcia certyfikatu TLS, głębokość kolejki zadań (ile oczekuje/trwa/nie powiodło się), łączny "drift" (wiadomości zachowane na serwerze docelowym mimo zniknięcia ze źródła), stan VM2 (health-check, zajętość dysku, ClamAV), ostatnie zdarzenia audytowe.

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
