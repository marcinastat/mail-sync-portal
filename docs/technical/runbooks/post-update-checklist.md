# Runbook: po `dnf update`

## VM2

Aktualizacje systemowe VM2 wykonuje się przez panel administracyjny
(`/admin` → dashboard → „Aktualizuj system") lub bezpośrednio przez
provisioning API: `POST /system/update`. Endpoint automatycznie uruchamia
health-check zaraz po aktualizacji i zwraca jego wynik oraz — jeśli wymagany
jest restart — jednorazowy token do `POST /system/reboot`. Wynik trafia też
do `audit_log` na VM2.

## VM1

VM1 nie ma odpowiednika provisioning API, więc `dnf update` wykonuje się
ręcznie po SSH:

```
sudo dnf -y update
sudo /mail-sync-portal/scripts/vm1/health-check.sh   # ścieżka klonu repo na serwerze
```

Skrypt sprawdza `firewalld`, `postgresql-<wersja>`, `nginx`, `php-fpm`,
`portal-gunicorn`, `portal-worker`, `portal-scheduler.timer`,
`portal-audit-verify.timer`, `fail2ban` i zwraca kod wyjścia różny od zera,
jeśli którakolwiek usługa nie jest aktywna.

nginx (VM1) i rspamd (VM2) są zablokowane przez `dnf versionlock` (patrz
`scripts/vm1/30-nginx.sh`, `scripts/vm2/45-rspamd.sh`). Jeśli świadomie chcesz
zmienić wersję, usuń blokadę (`dnf versionlock delete <pakiet>`) przed aktualizacją.

PostgreSQL **nie** jest blokowany: gałąź 17 trzyma sama nazwa pakietu
(`postgresql17-*`; wersja 18 to osobne pakiety), a wydania poprawkowe 17.x
(np. 17.10 → 17.11) instalują się w trybie „wszystkie” i nie wymagają
dump/restore. Pakiet PGDG sam restartuje `postgresql-17` w trakcie aktualizacji
(kilka sekund przerwy). Repo PGDG nie publikuje metadanych bezpieczeństwa, więc
tryb „tylko bezpieczeństwa” **nigdy** nie podnosi PostgreSQL. Po nowym wydaniu
17.x przejrzyj sekcję „Migration” w informacjach o wydaniu
(postgresql.org/docs/17/release-17-NN.html), bo czasem zaleca REINDEX dla
konkretnych rozszerzeń.

Jeśli `needs-restarting -r` (uruchamiane automatycznie przez VM2 API, ręcznie
na VM1: `sudo needs-restarting -r`) wskazuje na wymagany restart — zaplanuj
reboot w oknie serwisowym, po potwierdzeniu że health-check przechodzi.
