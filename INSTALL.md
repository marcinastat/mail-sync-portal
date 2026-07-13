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

## 0. Przygotowanie na obu VM

Na **VM1** i na **VM2** osobno:

```bash
sudo dnf -y install git
git clone https://github.com/marcinastat/mail-sync-portal.git
cd mail-sync-portal
cp config/install.conf.example config/install.conf
```

Otwórz `config/install.conf` (np. `nano config/install.conf`) i uzupełnij
**dokładnie te same wartości na obu VM** (to jeden wspólny plik konfiguracyjny):

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

Z Twojego komputera (albo z VM2 do VM1 bezpośrednio po SSH), skopiuj 3 pliki
z `mail-sync-portal/ca/` na VM2 do `/etc/portal/vm1-client/` na VM1:

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
  wykonanie danego kroku.
- `sudo scripts/vm1/health-check.sh` — szybki przegląd usług na VM1.
- Status usług: `systemctl status <nazwa>`, logi: `journalctl -u <nazwa> -e`.
- Pełny status faz projektu: `docs/technical/build-status.md`.
