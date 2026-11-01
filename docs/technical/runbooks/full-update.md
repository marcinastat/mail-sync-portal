# Runbook: pełna aktualizacja portalu (VM1 + VM2)

Procedura dla administratora z dostępem root do obu maszyn i kontem administratora panelu. Jest napisana tak, żeby dało się ją przejść **samodzielnie, bez kontaktu z dostawcą**.

Obejmuje:
1. nowy kod portalu (VM1) i API serwera poczty (VM2);
2. aktualizacje systemu (pakiety, w tym PostgreSQL 17.x i jądro);
3. aktualizację Roundcube (webmail).

Kod aktualizuje skrypt **`scripts/update.sh`**, który za każdym razem sam pobiera najnowszą wersję z repozytorium. Pakiety i Roundcube aktualizuje się z panelu.

**Czas:** ok. 30–45 minut. **Przerwy w działaniu:** webmail i synchronizacja kilka razy po 1–2 minuty, panel na czas restartu VM1. Zaplanuj okno serwisowe.

**Kolejność zawsze: najpierw VM2, potem VM1.**

---

## Krok 0. Przygotowanie

**0.1. Snapshot obu VM.** Zrób snapshot VM1 i VM2 **w tym samym momencie**, w hypervisorze. Maszyny współdzielą certyfikaty i dane, więc przywraca się je zawsze **obie naraz**. To ostateczna droga odwrotu z każdego kroku.

**0.2. Stan wyjściowy w panelu.** Na **Pulpicie** kafelek VM2 pokazuje dane, bez „brak połączenia”. Jeśli trwa synchronizacja, poczekaj, aż się skończy.

---

## Krok 1. Tylko przy pierwszej aktualizacji starszej instalacji

Jeśli w katalogu repozytorium jest już plik `scripts/update.sh`, **pomiń ten krok**.

Starsze instalacje nie mają jeszcze skryptu, a samo `git pull` może na nich nie zadziałać, bo historia repozytorium była zmieniana. Raz trzeba więc pobrać kod ręcznie, poleceniami z punktu 1.3.

**1.1. VM1: katalog repozytorium**
```bash
find / -xdev -maxdepth 4 -path '*/config/install.conf' 2>/dev/null
REPO=/mail-sync-portal          # podstaw wynik (bez /config/install.conf)
```

**1.2. VM2: katalog repozytorium.** Na VM2 bywają dwa katalogi z repo. Właściwy jest ten, w którym CA certyfikatów jest **identyczne z używanym przez API**:
```bash
A=$(openssl x509 -noout -fingerprint -sha256 -in /etc/portal/vm2-api/ca.crt)
for f in $(find / -xdev -maxdepth 4 -path '*/ca/ca.crt' 2>/dev/null); do
  [ "$(openssl x509 -noout -fingerprint -sha256 -in "$f")" = "$A" ] && echo "KATALOG REPO: ${f%/ca/ca.crt}"
done
REPO=/root/mail-sync-portal     # podstaw wynik
```
Jeśli nie pojawi się żaden wiersz `KATALOG REPO:`, **przerwij** i skontaktuj się z dostawcą. Nie instaluj niczego od nowa.

**1.3. Na obu VM: pobranie kodu**
```bash
umask 077; tar -czf /root/repo-backup-pierwszy-$(date +%Y%m%d-%H%M).tar.gz -C "$(dirname "$REPO")" "$(basename "$REPO")"
command -v git >/dev/null || dnf install -y git
cd "$REPO"
[ -d .git ] || { git init -q && git remote add origin https://github.com/marcinastat/mail-sync-portal.git; }
git fetch -q origin master && git reset --hard origin/master
ls scripts/update.sh config/install.conf
```
`config/install.conf` i katalog `ca/` są poza repozytorium, więc **zostają nietknięte**. Nie używaj `git clean`, bo by je usunął.

---

## Krok 2. VM2: aktualizacja kodu

```bash
cd /root/mail-sync-portal         # katalog repo VM2 (z kroku 1.2)
bash scripts/update.sh --check    # tylko kontrola, nic nie zmienia
bash scripts/update.sh            # właściwa aktualizacja
```
Skrypt kolejno:
1. sprawdza internet, adresy w `install.conf` i zgodność CA;
2. robi kopię katalogu repo (`/root/repo-backup-vm2-*.tar.gz`);
3. pobiera kod;
4. wdraża go;
5. zdejmuje dawną blokadę wersji PostgreSQL;
6. sprawdza usługi.

Na końcu wypisuje **„Aktualizacja kodu VM2 zakończona powodzeniem”** i co dalej.

**Jeśli skrypt się zatrzyma**, przy kontroli w punkcie 1 **nic nie zostało zmienione**. Komunikat mówi, co poprawić:

| Komunikat | Co zrobić |
|---|---|
| `Katalog … ma INNE CA niż wdrożone … Uruchom z katalogu: X` | przejdź do katalogu `X` i uruchom skrypt stamtąd |
| `VM2_IP=… nie jest adresem tej maszyny` | popraw adres w `config/install.conf` (na **obu** VM): `sed -i 's/^VM2_IP=.*/VM2_IP="<adres VM2>"/' config/install.conf`, potem uruchom ponownie |
| `VM1_IP=… różni się od wdrożonego` | jeśli `install.conf` ma zły adres, popraw go; jeśli VM1 naprawdę zmieniła adres, przejdź [runbook zmiany IP VM1](/admin/docs/technical/runbooks/vm1-ip-change) |
| `Lokalne zmiany w plikach repo` | ktoś zmieniał pliki repo ręcznie. Jeśli zmiany nie są potrzebne: `bash scripts/update.sh --force` (kopia powstanie) |
| `Brak dostępu do github.com` | maszyna musi mieć dostęp do internetu |

---

## Krok 3. VM1: aktualizacja kodu

```bash
cd /mail-sync-portal              # katalog repo VM1 (z kroku 1.1)
bash scripts/update.sh --check
bash scripts/update.sh
```
Skrypt robi to samo co na VM2. Dodatkowo:
- przed startem sprawdza, czy w panelu nie trwa żadna aktualizacja;
- na końcu testuje połączenie **VM1 → VM2**.

Oczekiwany wynik to **„Połączenie VM1 → VM2 (mTLS): OK”** i **„Aktualizacja kodu VM1 zakończona powodzeniem”**. Jeśli test połączenia zgłosi `403`, VM2 nie zna aktualnego adresu VM1 ([runbook zmiany IP VM1](/admin/docs/technical/runbooks/vm1-ip-change)).

W panelu odśwież **Pulpit** (Ctrl+F5): kafelek VM2 powinien pokazywać dane.

---

## Krok 4. Aktualizacje systemu (z panelu): najpierw VM2, potem VM1

Panel → **Ustawienia → Aktualizacje systemu**.

1. **VM2**: wybierz **„Wszystkie aktualizacje (pełny dnf update)”** → **Zainstaluj aktualizacje** → potwierdź. Tryb „wszystkie” jest potrzebny, bo tylko on obejmuje wydania PostgreSQL.
   - Okno postępu powinno skończyć się wynikiem **„gotowe”** i **„usługi OK”**. Podczas aktualizacji PostgreSQL baza sama restartuje się na kilka sekund.
   - Jeśli pojawi się **„wymagany restart”**, kliknij **„Uruchom ponownie teraz”**. Odczekaj ok. 2 minuty i odśwież stronę: odznaka zniknie, a na Pulpicie kafelek VM2 będzie pokazywał dane.
2. **VM1**: tak samo. Restart VM1 wyłącza panel na 1–2 minuty, po czym trzeba zalogować się ponownie.

Jeśli wynik to **„sprawdź wynik”**, kliknij **„Zapisz log do pliku”** i przejdź do sekcji „Gdy coś pójdzie nie tak”.

---

## Krok 5. Roundcube (z panelu)

Na tej samej stronie, karta **Roundcube (webmail)**:
1. Odznaka **„dostępna aktualizacja”** → **„Zaktualizuj Roundcube do …”** → potwierdź.
2. Webmail jest niedostępny ok. 1–2 minut. Wynik **„gotowe”** oznacza sukces.
3. Jeśli test po aktualizacji nie przejdzie, poprzednia wersja **wraca automatycznie**, a okno pokaże przyczynę.

Szczegóły: [runbook Roundcube](/admin/docs/technical/runbooks/roundcube-upgrade).

---

## Krok 6. Weryfikacja końcowa

| Co | Jak | Oczekiwane |
|---|---|---|
| Kod VM1 i VM2 | `bash scripts/update.sh --check` na każdej VM | „Kod jest aktualny” |
| PostgreSQL (obie VM) | `sudo -u postgres psql -tAc 'show server_version'` | najnowsze 17.x |
| Blokady wersji | `dnf -q versionlock list` | VM1: tylko nginx; VM2: tylko rspamd |
| Panel: Pulpit | kafelek VM2 | dane, bez błędu połączenia |
| Panel: Aktualizacje | karty VM1/VM2 i Roundcube | 0 łatek bezpieczeństwa, brak „wymagany restart”, Roundcube „aktualna” |
| Synchronizacja | dowolna skrzynka → „Synchronizuj teraz” | przebieg zakończony sukcesem |
| Webmail | logowanie na skrzynkę; „Otwórz w Roundcube”, jeśli włączone | skrzynka otwiera się poprawnie |

Po kilku dniach spokojnej pracy możesz usunąć snapshoty z kroku 0.

---

## Kolejne aktualizacje

Gdy instalacja ma już `scripts/update.sh`, każda kolejna aktualizacja to:
1. snapshot obu VM;
2. `bash scripts/update.sh` na VM2, potem na VM1. Skrypt sam pobiera najnowszy kod, także swoją nową wersję;
3. kroki 4–6 w panelu.

---

## Gdy coś pójdzie nie tak

Stan ostatniego przebiegu skryptu jest w `/var/lib/portal-update/last-run`, a pełny log w `/var/log/portal-update/`.

| Gdzie | Co się stało | Co zrobić |
|---|---|---|
| krok 1 | nie znaleziono katalogu z CA (VM2) | przerwij, skontaktuj się z dostawcą. Nie generuj nowego CA |
| krok 2–3 | skrypt zatrzymał się na kontroli | nic nie zostało zmienione; popraw według komunikatu (tabela w kroku 2) |
| krok 2–3 | błąd przy wdrożeniu lub weryfikacji | zapisz log. Powrót do poprzedniego kodu: `tar -xzf /root/repo-backup-<vm>-<data>.tar.gz -C "$(dirname "$REPO")"`, potem `FORCE_REAPPLY=1 bash scripts/vm2/50-provisioning-api.sh` (VM2) lub `… scripts/vm1/50-portal-app.sh` (VM1). Albo snapshot |
| krok 4 | aktualizacja „sprawdź wynik” | zapisz log z okna. Kopie configów: polecenie przywrócenia jest w oknie (`portal-config-recovery.sh` / `vm2-config-recovery.sh`) |
| krok 4 | maszyna nie wraca po restarcie | konsola hypervisora; w ostateczności snapshot **obu** VM |
| krok 5 | aktualizacja Roundcube nieudana | poprzednia wersja wróciła automatycznie; zapisz log z okna |
| dowolny | stan niejasny, panel nie działa | przywróć snapshot **obu** VM z kroku 0 |

### Co przesłać dostawcy, gdy potrzebna pomoc

- log skryptu: `/var/log/portal-update/update-<vm>-<data>.log` (z obu VM);
- log z okna aktualizacji w panelu („Zapisz log do pliku”);
- VM1: pliki z `/var/log/portal/system-updates/` oraz `journalctl -u portal-gunicorn -u portal-worker --since "-3h" > /root/vm1-journal.txt`;
- VM2: pliki z `/var/log/vm2-api/system-updates/` oraz `journalctl -u vm2-provisioning-api --since "-3h" > /root/vm2-journal.txt`;
- Roundcube: `/var/backups/roundcube/<katalog>/upgrade.log`.

**Nie wysyłaj:** `config/install.conf`, katalogu `ca/`, niczego z `/etc/portal/secrets/`, kopii `repo-backup-*.tar.gz` ani `config.inc.php` Roundcube. Zawierają hasła i klucze.
