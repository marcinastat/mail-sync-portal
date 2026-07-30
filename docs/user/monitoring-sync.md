# Monitorowanie synchronizacji

## Pulpit (`/admin/`)

Jeden ekran ze stanem całego środowiska: liczba aktywnych skrzynek, dni do wygaśnięcia certyfikatu TLS, głębokość kolejki zadań (ile oczekuje/trwa/nie powiodło się), łączny "drift" (wiadomości zachowane na serwerze docelowym mimo zniknięcia ze źródła), stan VM2 (health-check, zajętość **obu dysków** — systemowego i pocztowego — osobno, ClamAV), ostatnie zdarzenia audytowe.

## Monitoring dysków VM2

VM2 ma dwa dyski: systemowy i dedykowany na pocztę (`/var/mail/vhosts`). Zajętość obu jest sprawdzana dwutorowo:

- **lokalnie na VM2** co 15 minut (`vm2-disk-check.timer`) — ostrzeżenia trafiają do dziennika systemowego (`journalctl -u vm2-disk-check`), niezależnie od tego, czy VM1 w ogóle żyje;
- **z VM1** co 30 minut (razem z resztą health-checku VM2) — po przekroczeniu progu wysyła alert `disk_low_space` przez skonfigurowane kanały.

Próg ostrzeżenia (domyślnie 85%) ustawia się w `config/install.conf` (`DISK_USAGE_WARNING_PERCENT`).

## Lista skrzynek (`/admin/mailboxes`)

Pod ~50 skrzynek: **szukajka** (filtruje po adresie skrzynki i domenie źródłowej,
z licznikiem widocznych), **przyklejony nagłówek** i przewijanie **wewnątrz ramki**
(strona się nie rozjeżdża). „Zaznacz wszystkie" obejmuje tylko przefiltrowane wiersze.

## Widok skrzynki (`/admin/mailboxes/<id>`)

- Przycisk **„Synchronizuj teraz"** — wymusza natychmiastową synchronizację poza harmonogramem.
- **👁 Podgląd na żywo** — gdy synchronizacja trwa, modal pokazuje log imapsync
  **na bieżąco** (co się teraz dzieje: folder, postęp, ETA). Otwiera się też automatycznie,
  gdy wejdziesz na skrzynkę w trakcie synchronizacji; „w toku" w historii też do niego linkuje.
- **Historia synchronizacji** — domyślnie 10 ostatnich przebiegów (status, foldery,
  wiadomości u nas/na źródle, „drift", link do **surowego logu**) + przycisk **„Cała
  historia"** (modal z pełną listą).
- **Inwentaryzacja po dodaniu** — zaraz po zaprowizonowaniu nowej skrzynki leci przebieg
  „na sucho" (imapsync `--dry`): nic nie przenosi, tylko zbiera **ile jest do zebrania**
  (liczby/rozmiar źródła). Realny transfer robi dopiero kolejny przebieg — dzięki temu od
  razu widać skalę skrzynki. W audycie: `sync.completed` z `trigger=assess` („inwentaryzacja").
- **✉ Otwórz w Roundcube** (jeśli włączone w Ustawieniach) — podgląd skrzynki w webmailu
  bez hasła (dostęp administracyjny). Patrz „Otwórz w Roundcube".

## Throttling (`/admin/settings/throttle`)

Globalne limity: połączeń na minutę/godzinę/dzień oraz liczba równoległych synchronizacji. Kolejka respektuje te limity automatycznie — zadanie, które przekroczyłoby limit, jest po prostu odkładane na później, nie odrzucane.

## Alerty (`/admin/settings/alerts`)

Skonfiguruj kanał e-mail lub webhook i wybierz zdarzenia: nieudana synchronizacja, **wykrycie zagrożenia w skanie poczty** (`av_threat_found` — antywirus/phishing), problem z ClamAV na VM2, zbliżające się wygaśnięcie certyfikatu, niedostępność VM2, przekroczenie quoty domeny, naruszenie integralności logu audytowego. Alerty e-mail wymagają uzupełnienia `/etc/portal/alert-smtp.conf` na serwerze (zewnętrzny relay SMTP).

## Raporty (`/admin/reports`)

- **Podsumowanie** (kafelki): liczba skrzynek i aktywnych, wiadomości u nas / na źródle,
  **kompletność** (ile wiadomości jest na źródle a nie u nas — 0 = komplet) + drift,
  łączny rozmiar u nas, liczba błędów w ostatnich przebiegach.
- **Tabela per skrzynka**: domena źródłowa, sync (wł/wył), dni wstecz, ostatni przebieg
  (status · czas · trwanie · ewentualny błąd), wiadomości u nas / źródło, brakujące,
  rozmiar u nas / źródło, drift.
- **Wykrycia skanu poczty** — antywirus/phishing z podaniem **którego maila** dotyczą
  (temat, nadawca, data). Patrz „Skanowanie poczty".
- **Ochrona przed atakami (fail2ban)** — na dole strony: status blokad na obu serwerach
  (VM1 i VM2). Dla każdego jaila (SSH, logowanie do /admin, Roundcube, limity nginx)
  widać liczbę nieudanych prób, ile adresów jest aktualnie zablokowanych i **listę
  zbanowanych IP**. Widok jest tylko do odczytu — **odblokowanie robi administrator
  z konsoli** (bany są automatyczne i tymczasowe). Dokładne komendy do sprawdzania i
  odbanowania: dokumentacja techniczna „Runbook fail2ban".
- **Eksport CSV/PDF** — te same dane do dalszej obróbki lub jako gotowy raport.

Pełny log audytowy (`/admin/audit`) też eksportuje się do CSV/PDF.
