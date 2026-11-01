# Runbook: pełna aktualizacja portalu (VM1 + VM2)

Procedura dla administratora z dostępem root do obu maszyn i kontem administratora panelu. Jest napisana tak, żeby dało się ją przejść **samodzielnie, bez kontaktu z dostawcą**. Każdy krok mówi, czego się spodziewać i co zrobić, gdy wynik jest inny.

Obejmuje:
1. nowy kod portalu (VM1) i API serwera poczty (VM2);
2. aktualizacje systemu (pakiety, w tym PostgreSQL 17.x i jądro);
3. aktualizację Roundcube (webmail).

**Czas:** ok. 45–60 minut. **Przerwy w działaniu:** webmail i synchronizacja kilka razy po 1–2 minuty, panel na czas restartu VM1. Zaplanuj okno serwisowe.

Polecenia wykonujesz jako **root** w konsoli danej maszyny. W przykładach `10.0.0.10` to VM1, a `10.0.0.20` to VM2; podstaw swoje adresy.

---

## Krok 0. Przygotowanie

**0.1. Snapshot obu VM.** Zrób snapshot VM1 i VM2 **w tym samym momencie**, w hypervisorze. Maszyny współdzielą certyfikaty i dane, więc przywraca się je zawsze **obie naraz**. To ostateczna droga odwrotu z każdego kroku.

**0.2. Stan wyjściowy w panelu.**
- **Pulpit**: kafelek VM2 pokazuje dane (dysk, skan poczty), bez „brak połączenia”. Jeśli **trwa synchronizacja**, poczekaj, aż się skończy.
- **Ustawienia → Aktualizacje systemu**: zanotuj liczby łatek na VM1 i VM2.

**0.3. Dostęp do internetu** (na obu VM):
```bash
curl -sI https://github.com | head -1        # oczekiwane: HTTP/2 200 (lub HTTP/1.1 200)
```

---

## Krok 1. Znajdź katalog instalacyjny repozytorium

Portal instaluje się z katalogu z repozytorium. Na VM2 ten katalog zawiera też **CA certyfikatów mTLS**, więc wszystkie dalsze polecenia trzeba uruchamiać **z właściwego katalogu**.

**VM1:**
```bash
find / -xdev -maxdepth 4 -path '*/config/install.conf' 2>/dev/null
```
Wynik to `<katalog>/config/install.conf`, np. `/mail-sync-portal/config/install.conf`. Zapamiętaj katalog:
```bash
REPO=/mail-sync-portal          # podstaw swój wynik (bez /config/install.conf)
```

**VM2:** właściwy jest ten katalog, w którym CA jest **identyczne z używanym przez API**. Na VM2 bywają dwa katalogi z repo i tylko jeden jest właściwy.
```bash
A=$(openssl x509 -noout -fingerprint -sha256 -in /etc/portal/vm2-api/ca.crt)
for f in $(find / -xdev -maxdepth 4 -path '*/ca/ca.crt' 2>/dev/null); do
  [ "$(openssl x509 -noout -fingerprint -sha256 -in "$f")" = "$A" ] && echo "KATALOG REPO: ${f%/ca/ca.crt}"
done
```
Oczekiwany jest **dokładnie jeden** wiersz `KATALOG REPO: …`, np. `/root/mail-sync-portal`.
```bash
REPO=/root/mail-sync-portal     # podstaw swój wynik
```
- **Brak wiersza:** **przerwij procedurę** i skontaktuj się z dostawcą. Bez właściwego CA ponowne wdrożenie VM2 zerwałoby połączenie z panelem.
- **Więcej niż jeden wiersz:** wybierz dowolny, bo wszystkie mają to samo CA.

Jeśli przerwiesz sesję, ustaw `REPO` ponownie w każdej nowej sesji.

---

## Krok 2. Sprawdź adresy w `install.conf`

Skrypty wdrożeniowe biorą adresy z `install.conf`. Muszą one odpowiadać rzeczywistości, inaczej certyfikat lub allowlista API dostaną złe wartości.

Na **każdej** VM:
```bash
grep -E '^(VM1_IP|VM2_IP|VM1_HOSTNAME|VM2_HOSTNAME)=' "$REPO/config/install.conf"
hostname -I
```
Sprawdź:
- `VM1_IP` to aktualny adres VM1 (`hostname -I` na VM1);
- `VM2_IP` to aktualny adres VM2 (`hostname -I` na VM2).

Jeśli któryś adres się nie zgadza (np. maszyna dostała nowy adres z DHCP), popraw go **na obu VM**:
```bash
sed -i 's/^VM2_IP=.*/VM2_IP="10.0.0.20"/' "$REPO/config/install.conf"    # przykład dla VM2_IP
```
Jeśli zmienił się adres maszyny, a portal stracił połączenie, najpierw przejdź odpowiedni runbook: [zmiana adresu IP VM2](/admin/docs/technical/runbooks/vm2-ip-change) lub [zmiana adresu IP VM1](/admin/docs/technical/runbooks/vm1-ip-change).

---

## Krok 3. Kopia katalogu repozytorium

Na **każdej** VM. Kopia zawiera `install.conf`, a na VM2 także klucze CA, więc jest tylko dla roota:
```bash
umask 077
tar -czf /root/repo-backup-$(date +%Y%m%d-%H%M).tar.gz -C "$(dirname "$REPO")" "$(basename "$REPO")"
ls -la /root/repo-backup-*.tar.gz
```

---

## Krok 4. Pobierz nowy kod

Na **każdej** VM:
```bash
command -v git >/dev/null || dnf install -y git
cd "$REPO"
[ -d .git ] || { git init -q && git remote add origin https://github.com/marcinastat/mail-sync-portal.git; }
git fetch -q origin master
git reset --hard origin/master
git log --oneline -1
ls ca/ca.crt config/install.conf      # VM2: oba pliki muszą być; VM1: install.conf
```
Te polecenia działają w każdym układzie instalacji:
- zwykły klon git;
- starszy klon sprzed zmiany historii repozytorium, przy którym samo `git pull` by zawiodło;
- kopia bez `.git`, wgrana z VM1 skryptem `sync-to-vm2.sh`.

`config/install.conf` i katalog `ca/` są wyłączone z repozytorium, więc **zostają nietknięte**.

Nie używaj `git clean`: usunąłby `install.conf` i CA.

---

## Krok 5. Wdróż kod na VM2

```bash
cd "$REPO" && FORCE_REAPPLY=1 bash scripts/vm2/50-provisioning-api.sh
systemctl is-active vm2-provisioning-api          # oczekiwane: active
```
Skrypt **sam odmówi pracy, zanim cokolwiek zmieni**, jeśli:
- uruchamiasz go z katalogu z innym CA niż wdrożone. Komunikat wskaże właściwy katalog: wróć do kroku 1;
- `VM2_IP` nie jest adresem tej maszyny albo `VM1_IP` różni się od wdrożonego: wróć do kroku 2.

Ostrzeżenia `WARN … ręcznie zmieniony … kopia zapasowa` są normalne.

---

## Krok 6. Wdróż kod na VM1

```bash
cd "$REPO" && FORCE_REAPPLY=1 bash scripts/vm1/50-portal-app.sh
bash scripts/vm1/health-check.sh                   # oczekiwane: wszystkie OK
```
Test połączenia VM1 → VM2 (mTLS):
```bash
H=$(sudo -u postgres psql -d portal_db -tAc "select vm2_host||':'||vm2_api_port from vm2_connection")
curl -s -o /dev/null -w '%{http_code}\n' --cert /etc/portal/vm1-client/client.crt \
  --key /etc/portal/vm1-client/client.key --cacert /etc/portal/vm1-client/ca.crt "https://$H/health"
```
Oczekiwany kod to `200`. Pozostałe:
- `403`: allowlista VM2 nie zna adresu VM1. Patrz krok 2 i [runbook zmiany IP VM1](/admin/docs/technical/runbooks/vm1-ip-change).
- `000` / timeout: VM2 nieosiągalna. Sprawdź sieć i `systemctl status vm2-provisioning-api` na VM2.

W panelu odśwież **Pulpit** (Ctrl+F5): kafelek VM2 powinien pokazywać dane.

---

## Krok 7. Zdejmij blokadę wersji PostgreSQL (jednorazowo)

Starsze instalacje blokowały wersję PostgreSQL, co uniemożliwiało instalowanie wydań poprawkowych 17.x z łatkami bezpieczeństwa. Bieżące skrypty już tej blokady nie zakładają; na istniejącej maszynie trzeba ją zdjąć raz, ręcznie.

Na **każdej** VM:
```bash
dnf -q versionlock list | grep '^postgresql' | sed 's/-[0-9]*:.*//' | while read -r p; do dnf -q versionlock delete "$p" </dev/null; done
dnf -q versionlock list                          # VM1: zostaje nginx; VM2: zostaje rspamd
dnf update --assumeno 2>&1 | grep -E 'Problem|postgresql' | head
```
W ostatnim poleceniu **nie powinno być linii `Problem:`**. Pakiety `postgresql17*` mogą się pojawić na liście do aktualizacji, i tak ma być. Gdy blokad nie było, pętla nic nie robi i to też jest w porządku.

---

## Krok 8. Aktualizacje systemu (z panelu): najpierw VM2, potem VM1

Panel → **Ustawienia → Aktualizacje systemu**.

**8.1. VM2 (serwer poczty).**
1. Na karcie VM2 wybierz **„Wszystkie aktualizacje (pełny dnf update)”** → **Zainstaluj aktualizacje** → potwierdź. Tryb „wszystkie” jest konieczny, bo tylko on obejmuje wydania PostgreSQL.
2. Okno postępu powinno skończyć się wynikiem **„gotowe”** i **„usługi OK”**. Podczas aktualizacji PostgreSQL baza sama restartuje się na kilka sekund.
3. Jeśli pojawi się **„wymagany restart”**, kliknij **„Uruchom ponownie teraz”**. Odczekaj ok. 2 minuty i odśwież stronę: odznaka powinna zniknąć, a na Pulpicie kafelek VM2 pokazywać dane.

**8.2. VM1 (portal).** Tak samo jak dla VM2. Restart VM1 wyłącza panel na 1–2 minuty, po czym trzeba zalogować się ponownie.

Jeśli wynik to **„sprawdź wynik”** (błąd), zostaw okno otwarte, kliknij **„Zapisz log do pliku”** i przejdź do sekcji „Gdy coś pójdzie nie tak”.

---

## Krok 9. Aktualizacja Roundcube (z panelu)

Panel → **Ustawienia → Aktualizacje systemu** → karta **Roundcube (webmail)**.

1. Odznaka **„dostępna aktualizacja”** → kliknij **„Zaktualizuj Roundcube do …”** → potwierdź.
2. Webmail jest niedostępny ok. 1–2 minut. Wynik **„gotowe”** oznacza sukces.
3. Jeśli test po aktualizacji nie przejdzie, poprzednia wersja **wraca automatycznie**, a okno pokaże przyczynę. Webmail działa wtedy dalej na starej wersji.

Alternatywa z konsoli VM1: `cd "$REPO" && bash scripts/vm1/roundcube-upgrade.sh check`, potem `… upgrade` ([runbook Roundcube](/admin/docs/technical/runbooks/roundcube-upgrade)).

---

## Krok 10. Weryfikacja końcowa

| Co | Jak | Oczekiwane |
|---|---|---|
| Usługi VM1 | `cd "$REPO" && bash scripts/vm1/health-check.sh` | wszystkie `OK` |
| Usługi VM2 | `systemctl is-active postgresql-17 dovecot postfix vm2-provisioning-api` | wszystkie `active` |
| PostgreSQL (obie VM) | `sudo -u postgres psql -tAc 'show server_version'` | najnowsze 17.x |
| Blokady wersji | `dnf -q versionlock list` | VM1: tylko nginx; VM2: tylko rspamd |
| Panel: Pulpit | kafelek VM2 | dane, bez błędu połączenia |
| Panel: Aktualizacje | karty VM1/VM2 i Roundcube | 0 łatek bezpieczeństwa, brak „wymagany restart”, Roundcube „aktualna” |
| Synchronizacja | dowolna skrzynka → „Synchronizuj teraz” | przebieg zakończony sukcesem |
| Webmail | logowanie na skrzynkę; „Otwórz w Roundcube”, jeśli włączone | skrzynka otwiera się poprawnie |

Gdy wszystko się zgadza, możesz usunąć snapshoty z kroku 0 (po kilku dniach spokojnej pracy) i kopie `/root/repo-backup-*.tar.gz`.

---

## Gdy coś pójdzie nie tak

| Krok | Co się stało | Co zrobić |
|---|---|---|
| 1 | nie znaleziono katalogu z CA (VM2) | przerwij, skontaktuj się z dostawcą. Nie generuj nowego CA |
| 4 | błąd `git` / brak internetu | nic nie zostało wdrożone; popraw dostęp i powtórz. Repo przywrócisz z kopii: `tar -xzf /root/repo-backup-….tar.gz -C "$(dirname "$REPO")"` |
| 5–6 | skrypt przerwał z komunikatem o CA lub adresach | nic nie zostało zmienione; popraw według komunikatu i powtórz |
| 5–6 | skrypt przerwał w połowie z innym błędem | zapisz wyjście. Przywróć poprzedni kod: rozpakuj kopię repo (jak wyżej) i uruchom ten sam skrypt `50-…` ponownie; ewentualnie wróć do snapshotu |
| 6 | test mTLS ≠ 200 | patrz opis kodów w kroku 6 |
| 7 | nadal `Problem:` w `dnf update --assumeno` | nie aktualizuj w trybie „wszystkie”; zapisz wynik i skontaktuj się z dostawcą. Tryb „tylko łatki bezpieczeństwa” można użyć |
| 8 | aktualizacja „sprawdź wynik” | zapisz log z okna. Kopie configów: polecenie przywrócenia jest w oknie (`portal-config-recovery.sh` / `vm2-config-recovery.sh`) |
| 8 | maszyna nie wraca po restarcie | konsola hypervisora; w ostateczności przywróć snapshot **obu** VM |
| 9 | aktualizacja Roundcube nieudana | poprzednia wersja wróciła automatycznie; zapisz log z okna |
| dowolny | stan niejasny, panel nie działa | przywróć snapshot **obu** VM z kroku 0 |

### Co przesłać dostawcy, gdy potrzebna pomoc

- skopiowane wyjście polecenia, które zawiodło (z terminala);
- log z okna aktualizacji w panelu („Zapisz log do pliku”);
- VM1: pliki z `/var/log/portal/system-updates/` oraz `journalctl -u portal-gunicorn -u portal-worker --since "-3h" > /root/vm1-journal.txt`;
- VM2: pliki z `/var/log/vm2-api/system-updates/` oraz `journalctl -u vm2-provisioning-api --since "-3h" > /root/vm2-journal.txt`;
- Roundcube: `/var/backups/roundcube/<katalog>/upgrade.log`.

**Nie wysyłaj:** `config/install.conf`, katalogu `ca/`, niczego z `/etc/portal/secrets/`, kopii `repo-backup-*.tar.gz` ani `config.inc.php` Roundcube. Zawierają hasła i klucze.
