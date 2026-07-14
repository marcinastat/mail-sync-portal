# Instalacja krok po kroku (2x Rocky Linux 10, czyste minimalne instalacje)

Zakładam: masz dwie świeże VM z Rocky Linux 10 (Minimal), obie w tej samej
sieci, root/sudo na obu, i wiesz jakie IP/hostname będą miały (VM1 = portal,
VM2 = serwer poczty).

**VM2 musi mieć DWA dyski**: jeden systemowy (na nim jest zainstalowany
Rocky Linux) i jeden dodatkowy, całkowicie pusty (bez partycji, bez systemu
plików) — na niego trafi cała poczta. `scripts/vm2/25-mail-disk.sh` wykrywa
go automatycznie, formatuje (XFS) i montuje pod `/var/mail/vhosts`. Jeśli VM2
ma więcej niż 2 dyski, ustaw jawnie `VM2_MAIL_DISK=/dev/sdX` w
`config/install.conf` (patrz krok 0). VM1 wystarczy jeden dysk.

## 0. Przygotowanie repozytorium

Dwie opcje — wybierz jedną.

### Opcja A: git clone na obu VM osobno

Na **VM1** i na **VM2** osobno:

```bash
sudo dnf -y install git
git clone https://github.com/marcinastat/mail-sync-portal.git
cd mail-sync-portal
cp config/install.conf.example config/install.conf
```

### Opcja B: klonujesz tylko na VM1, stamtąd wypychasz na VM2

Na **VM1**:

```bash
sudo dnf -y install git
git clone https://github.com/marcinastat/mail-sync-portal.git
cd mail-sync-portal
cp config/install.conf.example config/install.conf
```

Uzupełnij `config/install.conf` (patrz niżej), potem:

```bash
sudo scripts/vm1/sync-to-vm2.sh
```

Skrypt sam wygeneruje klucz SSH na VM1, wypchnie go na VM2 (**poprosi o
hasło roota VM2 jednorazowo** — potem już nie), i zsynchronizuje całe
repozytorium na VM2 pod `/root/mail-sync-portal` (rsync, bezpieczne do
wielokrotnego uruchomienia po każdej zmianie). Skrypty `scripts/vm2/*.sh`
nadal uruchamiasz **ręcznie i po kolei bezpośrednio na VM2** (przez SSH) —
ten skrypt tylko przygotowuje tam pliki, niczego zdalnie nie instaluje.

### Konfiguracja (obie opcje)

Otwórz `config/install.conf` (np. `nano config/install.conf`) i uzupełnij
**dokładnie te same wartości wszędzie, gdzie plik istnieje** (jeśli używasz
Opcji B, wystarczy uzupełnić raz na VM1 — `sync-to-vm2.sh` skopiuje plik na VM2):

```
VM1_HOSTNAME="portal.twoja-firma.local"
VM1_IP="10.0.0.10"          # prawdziwe IP VM1
VM2_HOSTNAME="mail.twoja-firma.local"
VM2_IP="10.0.0.20"          # prawdziwe IP VM2
ADMIN_SUBNET_CIDR="10.0.0.0/24"   # z jakiej podsieci wolno wchodzić po SSH/HTTPS na VM1
```

Resztę wartości można na start zostawić domyślną.

## 1. VM2 najpierw (serwer poczty)

Na **VM2**, w katalogu `mail-sync-portal`, uruchamiaj po kolei — każdy skrypt
jako root, każdy da się bezpiecznie uruchomić ponownie jeśli coś przerwiesz:

```bash
sudo scripts/vm2/00-preflight.sh
sudo scripts/vm2/10-base-hardening.sh
sudo scripts/vm2/20-postgresql.sh
sudo scripts/vm2/25-mail-disk.sh
sudo scripts/vm2/30-postfix-dovecot.sh
sudo scripts/vm2/40-clamav.sh
sudo scripts/vm2/50-provisioning-api.sh
sudo scripts/vm2/60-firewall-rules.sh
sudo scripts/vm2/70-finalize.sh
```

Na końcu `50-provisioning-api.sh` wypisze się log w stylu:

```
Certyfikat kliencki dla VM1 gotowy w .../ca/vm1-client.{crt,key} — skopiuj go bezpiecznie na VM1
```

**To jest ważny krok — VM1 nie połączy się z VM2 bez tych plików.**

## 2. Skopiuj certyfikaty mTLS z VM2 na VM1

Jeśli używałeś **Opcji B** (kroku `sync-to-vm2.sh`) w kroku 0, na VM1 wystarczy:

```bash
sudo scripts/vm1/fetch-vm2-client-cert.sh
```

— pobierze `ca/vm1-client.{crt,key}` i `ca/ca.crt` z VM2 (tym samym kluczem
SSH co `sync-to-vm2.sh`) i zainstaluje je pod `/etc/portal/vm1-client/`.

Jeśli używałeś **Opcji A** (osobny `git clone` na każdej VM), skopiuj 3 pliki
ręcznie z `mail-sync-portal/ca/` na VM2 do `/etc/portal/vm1-client/` na VM1:

```bash
# uruchom to z VM2 (albo dostosuj do swojego sposobu łączenia się z VM1)
ssh root@VM1_IP "mkdir -p /etc/portal/vm1-client"
scp ca/vm1-client.crt root@VM1_IP:/etc/portal/vm1-client/client.crt
scp ca/vm1-client.key root@VM1_IP:/etc/portal/vm1-client/client.key
scp ca/ca.crt          root@VM1_IP:/etc/portal/vm1-client/ca.crt
```

## 3. VM1 (portal)

Na **VM1**, w katalogu `mail-sync-portal`:

```bash
sudo scripts/vm1/00-preflight.sh
sudo scripts/vm1/10-base-hardening.sh
sudo scripts/vm1/20-postgresql.sh
sudo scripts/vm1/30-nginx.sh
sudo scripts/vm1/40-roundcube.sh
sudo scripts/vm1/50-portal-app.sh
sudo scripts/vm1/60-imapsync.sh
sudo scripts/vm1/70-fail2ban-jails.sh
sudo scripts/vm1/80-firewall-rules.sh
sudo scripts/vm1/90-finalize.sh
```

Ostatni skrypt wypisze adres kreatora pierwszego uruchomienia, np.:

```
Otwórz https://portal.twoja-firma.local/admin/setup
```

## 4. Pierwsze uruchomienie w przeglądarce

Z komputera znajdującego się w podsieci `ADMIN_SUBNET_CIDR`:

1. Wejdź na `https://<VM1_HOSTNAME lub VM1_IP>/admin/setup`.
2. Przeglądarka pokaże ostrzeżenie o certyfikacie (self-signed, tak ma być —
   VM1 jest tylko wewnętrzna) — zaakceptuj wyjątek.
3. Przejdź kreator: konto admina → TOTP (zeskanuj kod aplikacją typu Google
   Authenticator) → zapisz kody odzyskiwania → potwierdź podsieć → test
   połączenia z VM2 (jeśli błąd, sprawdź krok 2 — certyfikaty mTLS) →
   logo/kolory.
4. Zaloguj się i wejdź w **Import XLS**, żeby zaimportować pierwsze skrzynki.

## Jeśli coś pójdzie nie tak

- Każdy skrypt loguje się czytelnie i można go uruchomić ponownie (jest
  idempotentny) — `FORCE_REAPPLY=1 sudo scripts/vmX/NN-*.sh` wymusza ponowne
  wykonanie danego kroku (uwaga: `00-preflight.sh` z `FORCE_REAPPLY=1` też
  ponownie doinstaluje pakiety bazowe — przydatne po `git pull`, jeśli
  wcześniej brakowało np. `openssl`/`rsync`).
- `sudo scripts/vm1/health-check.sh` — szybki przegląd usług na VM1.
- Status usług: `systemctl status <nazwa>`, logi: `journalctl -u <nazwa> -e`.
- Jeśli `clamd@scan` nie startuje z błędem `Can't create freshclam.dat` /
  `No supported database files found` — to znak, że masz starszą wersję repo
  sprzed poprawki uprawnień `/var/lib/clamav`; zrób `git pull` i uruchom
  ponownie `sudo scripts/vm2/40-clamav.sh`.
- **Aktualizacje systemu** robisz z panelu: **Ustawienia → Aktualizacje systemu**
  (domyślnie tylko łatki bezpieczeństwa, w tle, z podglądem postępu). Szczegóły:
  `docs/user/system-updates.md`.
- Gdyby aktualizacja coś rozłożyła — przed każdą robiona jest **kopia
  konfiguracji**, a na konsoli jest narzędzie ratunkowe:
  `sudo portal-config-recovery.sh list|restore <znacznik>` (VM1) oraz
  `sudo vm2-config-recovery.sh …` (VM2).
- Pełny status faz projektu: `docs/technical/build-status.md`.
