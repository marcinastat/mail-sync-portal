# Runbook: pełna aktualizacja portalu (VM1 + VM2)

Procedura dla administratora z dostępem root do obu maszyn i kontem administratora panelu. Jest napisana tak, żeby dało się ją przejść **samodzielnie, bez kontaktu z dostawcą**.

Aktualizacja składa się z trzech części:

| Część | Czym | Kolejność |
|---|---|---|
| 1. **Aplikacja** (kod panelu VM1 i API VM2) | jedno polecenie na VM **albo** przycisk w panelu | VM2, potem VM1 |
| 2. **Pakiety systemu** (w tym PostgreSQL 17.x, jądro) | panel | VM2, potem VM1 |
| 3. **Roundcube** (webmail) | panel | — |

**Czas:** ok. 30–45 minut. **Przerwy w działaniu:** panel, webmail i synchronizacja kilka razy po 1–2 minuty. Zaplanuj okno serwisowe.

---

## Krok 0. Przygotowanie

**0.1. Snapshot obu VM.** Zrób snapshot VM1 i VM2 **w tym samym momencie**, w hypervisorze. Maszyny współdzielą certyfikaty i dane, więc przywraca się je zawsze **obie naraz**. To ostateczna droga odwrotu z każdego kroku.

**0.2. Stan wyjściowy w panelu.** Na **Pulpicie** kafelek VM2 pokazuje dane, bez „brak połączenia”. Jeśli trwa synchronizacja, poczekaj, aż się skończy.

---

## Krok 1. Aplikacja

### 1A. Z konsoli: jedno polecenie na VM (zawsze działa, także na starszych instalacjach)

Jako **root**, najpierw na **VM2**, a gdy skończy, na **VM1**:
```bash
curl -fsSL https://raw.githubusercontent.com/marcinastat/mail-sync-portal/master/scripts/update.sh -o /root/portal-update.sh && bash /root/portal-update.sh
```
Skrypt kolejno:
1. rozpoznaje maszynę i **sam znajduje katalog instalacji** (na VM2 po certyfikacie CA, bo bywają tam dwa katalogi z repo);
2. robi kopię tego katalogu (`/root/repo-backup-<vm>-<data>.tar.gz`);
3. pobiera najnowszy kod (`config/install.conf` i CA zostają nietknięte);
4. sprawdza adresy i zgodność certyfikatów;
5. wdraża kod;
6. wykonuje jednorazowe migracje;
7. testuje usługi, a na VM1 także połączenie z VM2.

Na końcu wypisuje **„Aktualizacja aplikacji VM2/VM1 zakończona powodzeniem”** i następny krok.

Samą kontrolę, bez żadnych zmian, uruchomisz tak: `bash /root/portal-update.sh --check`.

### 1B. Z panelu (gdy obie VM mają już aktualną wersję z przyciskiem)

Panel → **Ustawienia → Aktualizacje systemu** → karta **Aplikacja portalu**. Karta pokazuje wersje VM1, VM2 i najnowszą na GitHub. Przycisk **„Aktualizuj aplikację”** robi to samo co 1A na obu maszynach, sam pilnując kolejności: najpierw VM2, potem VM1.

Pod koniec panel restartuje się na chwilę, ale okno postępu samo wznowi odczyt. Po wyniku **„gotowe”** odśwież stronę (Ctrl+F5). Jeśli karta pokazuje, że VM2 „nie obsługuje jeszcze aktualizacji z panelu”, zrób raz krok 1A.

### Gdy skrypt (lub okno w panelu) się zatrzyma

Zatrzymanie w kontroli wstępnej **niczego nie zmienia**. Komunikat mówi, co poprawić:

| Komunikat | Co zrobić |
|---|---|
| `VM2_IP=… nie jest adresem tej maszyny … Popraw <katalog>/config/install.conf` | popraw adres w podanym pliku (na **obu** VM): `sed -i 's/^VM2_IP=.*/VM2_IP="<adres VM2>"/' <katalog>/config/install.conf`, potem uruchom polecenie ponownie |
| `VM1_IP=… różni się od wdrożonego` | jeśli `install.conf` ma zły adres, popraw go; jeśli VM1 naprawdę zmieniła adres, przejdź [runbook zmiany IP VM1](/admin/docs/technical/runbooks/vm1-ip-change) |
| `Katalog … ma INNE CA niż wdrożone … Uruchom z katalogu: X` | uruchom ponownie z `PORTAL_REPO=X bash /root/portal-update.sh` |
| `Nie znaleziono katalogu repo z CA wdrożonym na tej VM2` | **przerwij**, skontaktuj się z dostawcą. Nie instaluj niczego od nowa |
| `Lokalne zmiany w plikach repo` | ktoś zmieniał pliki repo ręcznie. Jeśli zmiany nie są potrzebne: `bash /root/portal-update.sh --force` (kopia powstanie) |
| `Brak dostępu do github.com` | maszyna musi mieć dostęp do internetu |
| `VM2 odrzuca adres VM1 (403)` (na VM1) | VM2 nie zna aktualnego adresu VM1: [runbook zmiany IP VM1](/admin/docs/technical/runbooks/vm1-ip-change) |

---

## Krok 2. Pakiety systemu (z panelu): najpierw VM2, potem VM1

Panel → **Ustawienia → Aktualizacje systemu**.

1. **VM2**: wybierz **„Wszystkie aktualizacje (pełny dnf update)”** → **Zainstaluj aktualizacje** → potwierdź. Tryb „wszystkie” jest potrzebny, bo tylko on obejmuje wydania PostgreSQL.
   - Okno postępu powinno skończyć się wynikiem **„gotowe”** i **„usługi OK”**. Podczas aktualizacji PostgreSQL baza sama restartuje się na kilka sekund.
   - Jeśli pojawi się **„wymagany restart”**, kliknij **„Uruchom ponownie teraz”**. Odczekaj ok. 2 minuty i odśwież stronę: odznaka zniknie, a na Pulpicie kafelek VM2 będzie pokazywał dane.
2. **VM1**: tak samo. Restart VM1 wyłącza panel na 1–2 minuty, po czym trzeba zalogować się ponownie.

Jeśli wynik to **„sprawdź wynik”**, kliknij **„Zapisz log do pliku”** i przejdź do sekcji „Gdy coś pójdzie nie tak”.

---

## Krok 3. Roundcube (z panelu)

Na tej samej stronie, karta **Roundcube (webmail)**:
1. Odznaka **„dostępna aktualizacja”** → **„Zaktualizuj Roundcube do …”** → potwierdź.
2. Webmail jest niedostępny ok. 1–2 minut. Wynik **„gotowe”** oznacza sukces.
3. Jeśli test po aktualizacji nie przejdzie, poprzednia wersja **wraca automatycznie**, a okno pokaże przyczynę.

Szczegóły: [runbook Roundcube](/admin/docs/technical/runbooks/roundcube-upgrade).

---

## Krok 4. Weryfikacja końcowa

| Co | Jak | Oczekiwane |
|---|---|---|
| Aplikacja | karta „Aplikacja portalu” | VM1 i VM2 = najnowsza, odznaka „aktualna” |
| Pakiety | karty VM1 i VM2 | 0 łatek bezpieczeństwa, brak „wymagany restart” |
| Roundcube | karta „Roundcube (webmail)” | „aktualna” |
| PostgreSQL (obie VM) | `sudo -u postgres psql -tAc 'show server_version'` | najnowsze 17.x |
| Pulpit | kafelek VM2 | dane, bez błędu połączenia |
| Synchronizacja | dowolna skrzynka → „Synchronizuj teraz” | przebieg zakończony sukcesem |
| Webmail | logowanie na skrzynkę; „Otwórz w Roundcube”, jeśli włączone | skrzynka otwiera się poprawnie |

Po kilku dniach spokojnej pracy możesz usunąć snapshoty z kroku 0.

---

## Gdy coś pójdzie nie tak

Stan ostatniej aktualizacji aplikacji jest w `/var/lib/portal-update/last-run` (z panelu: `app-run`), a pełne logi w `/var/log/portal-update/`.

| Gdzie | Co się stało | Co zrobić |
|---|---|---|
| krok 1 | zatrzymanie w kontroli | nic nie zostało zmienione; popraw według tabeli w kroku 1 |
| krok 1 | błąd przy wdrożeniu lub teście | zapisz log. Powrót do poprzedniego kodu: rozpakuj kopię `tar -xzf /root/repo-backup-<vm>-<data>.tar.gz -C <katalog nadrzędny>`, potem z katalogu instalacji `FORCE_REAPPLY=1 bash scripts/vm2/50-provisioning-api.sh` (VM2) lub `… scripts/vm1/50-portal-app.sh` (VM1). Albo snapshot |
| krok 2 | aktualizacja „sprawdź wynik” | zapisz log z okna. Kopie configów: polecenie przywrócenia jest w oknie (`portal-config-recovery.sh` / `vm2-config-recovery.sh`) |
| krok 2 | maszyna nie wraca po restarcie | konsola hypervisora; w ostateczności snapshot **obu** VM |
| krok 3 | aktualizacja Roundcube nieudana | poprzednia wersja wróciła automatycznie; zapisz log z okna |
| dowolny | stan niejasny, panel nie działa | przywróć snapshot **obu** VM z kroku 0 |

### Co przesłać dostawcy, gdy potrzebna pomoc

- logi z `/var/log/portal-update/` (z obu VM);
- log z okna aktualizacji w panelu („Zapisz log do pliku”);
- VM1: pliki z `/var/log/portal/system-updates/` oraz `journalctl -u portal-gunicorn -u portal-worker --since "-3h" > /root/vm1-journal.txt`;
- VM2: pliki z `/var/log/vm2-api/system-updates/` oraz `journalctl -u vm2-provisioning-api --since "-3h" > /root/vm2-journal.txt`;
- Roundcube: `/var/backups/roundcube/<katalog>/upgrade.log`.

**Nie wysyłaj:** `config/install.conf`, katalogu `ca/`, niczego z `/etc/portal/secrets/`, kopii `repo-backup-*.tar.gz` ani `config.inc.php` Roundcube. Zawierają hasła i klucze.
