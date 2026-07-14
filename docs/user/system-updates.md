# Aktualizacje systemu

Portal pozwala instalować aktualizacje obu maszyn (VM1 „portal" i VM2 „serwer poczty")
bez logowania się po SSH — z poziomu **Ustawienia → Aktualizacje systemu**
(`/admin/settings/updates`).

## Domyślnie tylko łatki bezpieczeństwa

Rocky Linux 10 udostępnia metadane errat bezpieczeństwa, więc domyślnym (i zalecanym)
trybem jest **tylko bezpieczeństwo** — pod spodem `dnf --security update`. Świadomie
unikamy pełnego `dnf update`, który mógłby przeskoczyć wersje i coś rozłożyć.

Strona pokazuje dla każdej maszyny:

- liczbę oczekujących **łatek bezpieczeństwa** (czerwony znacznik, jeśli >0),
- liczbę **wszystkich** dostępnych aktualizacji,
- czy po aktualizacji będzie wymagany **restart** (np. nowy kernel).

## Jak to działa pod spodem

Aktualizacje nie mogą być instalowane bezpośrednio przez usługę portalu ani API VM2,
bo obie działają w piaskownicy systemd (`ProtectSystem`), która blokuje zapis do
`/usr` i `/var`. Dlatego `dnf` jest uruchamiany jako **jednostka przejściowa** przez
`systemd-run` — poza piaskownicą usługi. Po zakończeniu portal automatycznie wykonuje
**health-check** kluczowych usług (na VM1: PostgreSQL, nginx, gunicorn, worker, PHP-FPM,
fail2ban; na VM2: PostgreSQL, Dovecot, Postfix, ClamAV, API) i pokazuje wynik oraz
ewentualną potrzebę restartu.

## Wersje kluczowych pakietów są zablokowane

PostgreSQL 17 (obie VM) oraz nginx (VM1) mają **versionlock** — pełny `dnf update`
nie przeskoczy ich na nową wersję major i nie rozłoży bazy ani serwera WWW. Dovecot,
Postfix i ClamAV są aktualizowane w ramach wydań point-release systemu (bezpieczne).

## Restart po aktualizacji

Jeśli portal zasygnalizuje „zalecany reboot" (zwykle po aktualizacji kernela lub
kluczowych bibliotek), zrestartuj maszynę w dogodnym oknie. Wszystkie usługi są
`enabled` i wstają samoczynnie po restarcie; dysk pocztowy VM2 jest w `fstab`
z opcją `nofail`. Po restarcie warto zajrzeć na [Pulpit](/admin/) i potwierdzić,
że synchronizacja i połączenie z VM2 działają.
