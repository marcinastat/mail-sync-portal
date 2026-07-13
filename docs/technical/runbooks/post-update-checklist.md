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
sudo n:/OBSZA_APKI/scripts/vm1/health-check.sh   # ścieżka lokalna repo na serwerze
```

Skrypt sprawdza `firewalld`, `postgresql-<wersja>`, `nginx`, `php-fpm`,
`portal-gunicorn`, `portal-worker`, `portal-scheduler.timer`,
`portal-audit-verify.timer`, `fail2ban` i zwraca kod wyjścia różny od zera,
jeśli którakolwiek usługa nie jest aktywna.

Pakiety PostgreSQL i nginx są zablokowane przez `dnf versionlock` (patrz
`scripts/vm1/20-postgresql.sh`, `scripts/vm1/30-nginx.sh`,
`scripts/vm2/20-postgresql.sh`) — zwykły `dnf update` nie przeskoczy ich na
inną gałąź główną. Jeśli świadomie chcesz zmienić wersję, usuń blokadę
(`dnf versionlock delete <pakiet>`) przed aktualizacją.

Jeśli `needs-restarting -r` (uruchamiane automatycznie przez VM2 API, ręcznie
na VM1: `sudo needs-restarting -r`) wskazuje na wymagany restart — zaplanuj
reboot w oknie serwisowym, po potwierdzeniu że health-check przechodzi.
