# Runbook: aktualizacja Roundcube

Roundcube (webmail na VM1) jest instalowany z oficjalnej paczki (`40-roundcube.sh`), a **nie z dnf**. Dlatego aktualizacje systemu, ani z panelu, ani `dnf update`, **nie obejmują Roundcube**. Wydania Roundcube często zawierają poprawki bezpieczeństwa (XSS, SSRF, wstrzykiwanie poleceń IMAP), więc aktualizuj go regularnie.

Służy do tego narzędzie konsolowe `scripts/vm1/roundcube-upgrade.sh`. Działa tak samo na każdej instalacji portalu, także u klienta: nic w nim nie zależy od konkretnej maszyny (adresów, nazw hostów).

## Co robi narzędzie (bezpieczniki)

1. **Kontrola wstępna, bez zmian**: instalacja Roundcube w `/var/www/roundcube`, dostęp do bazy `roundcube_db`, wymagane narzędzia, wolne miejsce na kopię.
2. **Weryfikacja paczki**: pobiera `roundcubemail-<wersja>-complete.tar.gz` z GitHuba i sprawdza podpis GPG kluczem „Roundcube Developers” (odcisk przypięty w `scripts/lib/roundcube.sh`). Niepoprawny podpis kończy działanie, zanim cokolwiek zostanie zmienione.
3. **Kopia zapasowa**: pliki `/var/www/roundcube` i baza `roundcube_db` (`pg_dump`) trafiają do `/var/backups/roundcube/<data>-<wersja>/`. Trzymane są 3 ostatnie kopie.
4. **Podmiana**: na czas instalacji webmail jest zatrzymany (`php-fpm`), żeby nie obsługiwał w połowie zaktualizowanego kodu. Instalacja idzie oficjalnym `bin/installto.sh`: nie rusza `config/config.inc.php` i zostawia dodatkowe wtyczki (`portal_sso`) oraz logo; schemat bazy aktualizuje `bin/update.sh`.
5. **Test po aktualizacji**:
   - wersja się zgadza;
   - `php-fpm` działa;
   - Roundcube uruchamia się z konfiguracją, wtyczkami i połączeniem z bazą;
   - strona logowania odpowiada.
6. **Automatyczne cofnięcie**: jeśli instalacja, aktualizacja bazy lub test nie przejdzie, narzędzie samo przywraca pliki i bazę z kopii z punktu 3.

Domyślnie aktualizacja zostaje **w tej samej gałęzi** (np. 1.7.x → najnowsza 1.7.x). Zmiana gałęzi (np. 1.6 → 1.7) wymaga świadomej decyzji, opisanej niżej.

## Procedura (VM1, root)

```bash
cd /mail-sync-portal            # klon repo na VM1
git pull                        # najnowsza wersja narzędzia

# 1. Sprawdzenie, bez żadnych zmian: wersje + kontrola wstępna
bash scripts/vm1/roundcube-upgrade.sh check

# 2. Aktualizacja do najnowszej wersji w gałęzi (albo jawnie: upgrade 1.7.5)
bash scripts/vm1/roundcube-upgrade.sh upgrade
```

Aktualizacja trwa zwykle 1–2 minuty, a webmail jest w tym czasie niedostępny. Rób ją, gdy nikt nie pracuje w Roundcube. Synchronizacje (imapsync) i panel `/admin` działają normalnie, bo nie korzystają z Roundcube.

Po udanej aktualizacji narzędzie wpisuje nową wersję do `config/install.conf` (`ROUNDCUBE_VERSION`).

## Sprawdzenie po aktualizacji

1. Zaloguj się do webmaila na dowolną skrzynkę.
2. Jeśli używasz „Otwórz w Roundcube” (Ustawienia → Otwórz w Roundcube), otwórz skrzynkę z panelu i sprawdź, że loguje się na właściwą.
3. Logo w webmailu jest na miejscu.

Jeśli narzędzie zgłosi `HTTP 403` z 127.0.0.1, to nie jest błąd: strefy dostępu w panelu nie wpuszczają lokalnego adresu. Sprawdzenie w przeglądarce (punkt 1) wystarczy.

## Cofnięcie ręczne

```bash
bash scripts/vm1/roundcube-upgrade.sh list                       # kopie (z wersjami)
bash scripts/vm1/roundcube-upgrade.sh rollback /var/backups/roundcube/<katalog>
```

Rollback przywraca pliki i bazę `roundcube_db`. Bieżący katalog przenosi do `/var/www/roundcube.failed-<data>`, żeby można go było obejrzeć; usuń go po sprawdzeniu, bo zawiera konfigurację z hasłem do bazy. Kopia bazy obejmuje kontakty, ustawienia i tożsamości użytkowników zapisane w Roundcube. Zmiany zrobione przez użytkowników **po** aktualizacji zostaną cofnięte razem z nią. Sama poczta leży na VM2 i rollback jej nie dotyczy.

Automatyczne cofnięcie można wyłączyć (np. żeby zbadać nieudaną aktualizację na żywo): `NO_AUTO_ROLLBACK=1 bash scripts/vm1/roundcube-upgrade.sh upgrade`. Narzędzie wypisze wtedy polecenie `rollback` do ręcznego użycia.

## Zmiana gałęzi (np. 1.6 → 1.7)

Nowa gałąź może zmieniać konfigurację, wymagania PHP i wtyczki. Przed zmianą:
1. Przeczytaj sekcję **UPGRADING** w informacjach o wydaniu (github.com/roundcube/roundcubemail/releases).
2. Uruchom z jawną zgodą:
   ```bash
   ALLOW_BRANCH_CHANGE=1 bash scripts/vm1/roundcube-upgrade.sh upgrade 1.7.5
   ```
Bezpieczniki są te same (kopia, test, automatyczne cofnięcie). Jeśli `update.sh` dostosuje `config.inc.php` do nowej gałęzi, poprzednia wersja zostanie w `config/config.inc.php.old.php`.

## Typowe problemy

- **„Nie udało się pobrać listy wydań z GitHub”**: brak dostępu do internetu albo limit GitHub API. Podaj wersję jawnie: `upgrade 1.7.5`. Paczka i tak pochodzi z GitHuba, więc dostęp wychodzący do `github.com` i `roundcube.net` (klucz GPG) jest konieczny.
- **„Podpis GPG NIEPOPRAWNY”**: paczka nie pochodzi od Roundcube albo została uszkodzona w drodze. Nic nie zostało zmienione. Nie obchodź tej kontroli.
- **„Za mało miejsca na /var”**: zwolnij miejsce (np. stare kopie w `/var/backups/roundcube`) i uruchom ponownie.
- **„Inna aktualizacja Roundcube już trwa”**: narzędzie chroni się blokadą przed równoległym uruchomieniem. Poczekaj, aż poprzednie skończy pracę.
- **Pełny log instalacji**: `/var/backups/roundcube/<katalog>/upgrade.log`.
