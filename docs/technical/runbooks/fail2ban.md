# Runbook: fail2ban (podgląd, diagnostyka, unban)

fail2ban blokuje adresy IP po serii nieudanych logowań. Działa na **obu** serwerach:

| Serwer | Jaile | Chroni |
|---|---|---|
| **VM1 (portal)** | `sshd`, `portal-admin-auth`, `roundcube-auth`, `nginx-limit-req` | SSH, logowanie do /admin, logowanie do Roundcube, nadużycia limitów nginx |
| **VM2 (serwer poczty)** | `sshd` | SSH (dostęp do maildirów tylko z podsieci admin) |

Konfiguracja jaili: `/etc/fail2ban/jail.d/` (`jail-portal.conf` na VM1, `vm2.conf` na VM2). Backend to **systemd** (Rocky Minimal loguje do journala, nie ma `/var/log/secure`).

## 1. Podgląd w panelu (read-only)
**Raporty → sekcja „Ochrona przed atakami (fail2ban)"** — na dole strony. Widać per serwer: listę jaili, liczbę nieudanych prób (teraz/łącznie), zbanowanych (teraz/łącznie) i **listę zbanowanych IP**. Widok jest tylko do odczytu — **odbanowanie robi się z konsoli** (niżej), świadomie: żeby przypadkowy klik nie zdejmował ochrony.

## 2. Diagnostyka z konsoli (root)
Wszystkie komendy jako root, na odpowiednim serwerze (na VM2 zaloguj się po SSH lub przez VM1).

```bash
# Ogólny status: ile jaili i jakie
fail2ban-client status

# Szczegóły jednego jaila: nieudane, zbanowane, LISTA zbanowanych IP
fail2ban-client status sshd
fail2ban-client status portal-admin-auth

# Czy usługa w ogóle działa
systemctl status fail2ban --no-pager

# Log na żywo (kto banowany, błędy filtrów, start jaili)
journalctl -u fail2ban -f
journalctl -u fail2ban --since "1 hour ago" --no-pager

# Sprawdź konkretne IP — czy i gdzie jest zbanowane
fail2ban-client banned            # wszystkie bany, per jail
fail2ban-client get sshd banned   # lista IP w danym jailu
```

Kiedy IP jest zbanowane, ruch z niego jest **odrzucany na firewallu** (fail2ban dodaje regułę). Objaw u klienta: „nie mogę się połączyć/zalogować, a chwilę temu działało" — najpierw sprawdź, czy jego IP nie wpadło w ban.

## 3. Odbanowanie (unban)
```bash
# Odbanuj KONKRETNE IP w konkretnym jailu
fail2ban-client set sshd unbanip 203.0.113.10

# To samo dla logowania do panelu / Roundcube
fail2ban-client set portal-admin-auth unbanip 203.0.113.10
fail2ban-client set roundcube-auth   unbanip 203.0.113.10

# Odbanuj IP niezależnie od jaila (fail2ban sam znajdzie właściwy)
fail2ban-client unban 203.0.113.10

# Odbanuj WSZYSTKO (ostrożnie — zdejmuje całą ochronę bieżącą)
fail2ban-client unban --all
```

## 4. Ręczny ban (gdy trzeba szybko zablokować napastnika)
```bash
fail2ban-client set sshd banip 203.0.113.66
```

## 5. Trwałe wyłączenie IP z banowania (whitelist administratora)
Żeby zaufany adres (np. biuro/VPN admina) NIGDY nie był banowany — dodaj go do `ignoreip` i przeładuj:
```bash
# w /etc/fail2ban/jail.d/jail-portal.conf (VM1) lub vm2.conf (VM2), w sekcji [DEFAULT] lub danym [jail]:
#   ignoreip = 127.0.0.1/8 ::1 192.168.10.0/24
fail2ban-client reload            # przeładuj konfigurację bez utraty stanu
```
Uwaga: zmiana w pliku pod `/etc/fail2ban/jail.d/` jest trwała między restartami; `unban` jest tylko doraźny (do następnego bana).

## 6. Parametry banów (gdzie zmienić)
W plikach jaili (`/etc/fail2ban/jail.d/`):
- `maxretry` — po ilu próbach ban,
- `findtime` — w jakim oknie liczone są próby,
- `bantime` — jak długo ban (np. `1h`; `-1` = na stałe).
Po edycji: `fail2ban-client reload`.

## 7. Typowe problemy
- **„Number of jail: 0"** — brak plików w `/etc/fail2ban/jail.d/` (fail2ban 1.x nie włącza jaili sam). Sprawdź, że istnieje `jail-portal.conf`/`vm2.conf`; te instalują skrypty `10-base-hardening.sh`.
- **fail2ban nie startuje** — najczęściej jail wskazuje log, którego nie ma. Na Rocky Minimal MUSI być `backend = systemd` (bez tego szuka `/var/log/secure`, którego nie ma, i odmawia startu). `journalctl -u fail2ban` pokaże przyczynę.
- **Panel: „brak połączenia" przy VM2** — vm2-api niedostępne lub mTLS; status VM2 idzie przez API na porcie 8443.

## Jak panel to czyta (dla utrzymania)
- VM1: `services/fail2ban_service.py` woła przez sudo root-owned `/opt/portal-app/bin/fail2ban-status.sh` (read-only, tylko `fail2ban-client status`), parsuje wynik.
- VM2: vm2-api `GET /fail2ban/status` (`services/fail2ban_control.py` + `/usr/local/sbin/vm2-fail2ban-status.sh`), pobierane przez mTLS (`vm2_client.fail2ban_status`).
- Helpery są root-owned i **nie przyjmują argumentów** — nie da się nimi banować/odbanować, wyłącznie odczyt.
