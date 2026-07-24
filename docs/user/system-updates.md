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
- czy jest wymagany **restart** (np. nowy kernel).

Liczby dociągają się w tle zaraz po wejściu na stronę (widać krótkie „sprawdzam…"),
bo `dnf` musi najpierw pobrać metadane repozytoriów — dzięki temu sama strona
otwiera się natychmiast, bez czekania.

## Przebieg aktualizacji — widać postęp na żywo

Po kliknięciu **Zainstaluj aktualizacje** aktualizacja rusza **w tle** (wykonuje ją
worker portalu), a na ekranie pojawia się okno postępu pokazujące kolejne fazy:

1. **Kopia zapasowa konfiguracji** — przed czymkolwiek robiony jest backup plików
   konfiguracyjnych (patrz niżej).
2. **Pobieranie i instalacja pakietów** (`dnf`) — najdłuższa faza.
3. **Test kluczowych usług** (health-check) — sprawdzenie, czy wszystko wstało.
4. **Sprawdzenie, czy wymagany restart.**

Okno można zamknąć i wrócić później — po ponownym wejściu na stronę, jeśli
aktualizacja nadal trwa, okno postępu otworzy się samo. Aktualizacja **nie**
blokuje już przeglądarki ani panelu.

## Kopia konfiguracji przed aktualizacją + narzędzie ratunkowe

> **Kopia obejmuje TYLKO pliki konfiguracyjne — nie dane ani maile.** To celowe:
> chroni przed sytuacją, gdy aktualizacja pakietu nadpisze nasze configi
> (np. własny `nginx.conf`, unit systemd, `dovecot`/`postfix`). Kopię **danych**
> (maile, bazy) robi się snapshotem całej VM po stronie hypervisora — to inny,
> szerszy mechanizm i celowo poza zakresem portalu.

Przed każdą aktualizacją portal robi **kopię plików konfiguracyjnych** (nginx,
portal, sudoers, systemd, PostgreSQL `*.conf` na VM1; Postfix, Dovecot, ClamAV,
PostgreSQL na VM2). Kopie trafiają do:

- VM1: `/var/lib/portal-config-backups/<znacznik-czasu>/`
- VM2: `/var/lib/vm2-config-backups/<znacznik-czasu>/`

(trzymane jest 10 ostatnich). `<znacznik-czasu>` to nazwa katalogu kopii, np.
`20260724-100107` — portal pokazuje go w oknie po aktualizacji razem z gotową
komendą przywrócenia.

### Jak przywrócić configi

Na **konsoli maszyny** (SSH/lokalnie, jako root):

```
# VM1
sudo portal-config-recovery.sh list                 # pokaż dostępne kopie (ze znacznikami)
sudo portal-config-recovery.sh show   <znacznik>     # co dokładnie jest w kopii
sudo portal-config-recovery.sh restore <znacznik>    # przywróć (wpisz znacznik, by potwierdzić)

# VM2 — identycznie
sudo vm2-config-recovery.sh list / show / restore <znacznik>
```

`restore` najpierw zapisuje bieżący stan (kopia `pre-restore-…`, więc restore
też da się cofnąć), potem przywraca wybraną kopię, przeładowuje systemd i
restartuje kluczowe usługi. Na koniec wypisuje stan usług.

## Log z aktualizacji (na maszynie + do pobrania)

Pełne wyjście każdej aktualizacji jest zapisywane w **trwałym logu na maszynie,
która ją wykonała**:

- VM1: `/var/log/portal/system-updates/vm1-run<id>-<czas>.log`
- VM2: `/var/log/vm2-api/system-updates/vm2-<tryb>-<czas>.log`

(dla aktualizacji VM2 portal trzyma dodatkowo kopię logu na VM1). W oknie
postępu, po zakończeniu, jest też przycisk **„Zapisz log do pliku"** — pobiera
całe wyjście do pliku lokalnie w przeglądarce. Ścieżkę logu na maszynie okno
pokazuje wprost.

## Restart po aktualizacji

Jeśli po aktualizacji wymagany jest restart (zwykle po kernelu lub kluczowych
bibliotekach), w oknie postępu **oraz** na karcie maszyny pojawia się przycisk
**Uruchom ponownie**. Restart jest osobną, świadomą decyzją — nie następuje
automatycznie. Wszystkie usługi są `enabled` i wstają po restarcie; dysk pocztowy
VM2 jest w `fstab` z `nofail`.

> Wykrywanie „czy wymagany restart" opiera się na `needs-restarting -r` (pakiet
> `dnf-utils`, instalowany na obu VM). Gdy narzędzia brak, portal pokazuje stan
> „nieznany" — **nie** zgaduje na siłę „wymagany" (to był wcześniejszy błąd, przez
> który restart wydawał się wymagany także tuż po restarcie).

## Wersje kluczowych pakietów są zablokowane

PostgreSQL 17 (obie VM) oraz nginx (VM1) mają **versionlock** — pełny `dnf update`
nie przeskoczy ich na nową wersję major i nie rozłoży bazy ani serwera WWW. Dovecot,
Postfix i ClamAV są aktualizowane w ramach wydań point-release systemu (bezpieczne).

## Jak to działa pod spodem

Aktualizacje nie mogą być instalowane bezpośrednio przez usługę portalu ani API VM2,
bo obie działają w piaskownicy systemd (`ProtectSystem`), która blokuje zapis do
`/usr` i `/var`. Dlatego `dnf` jest uruchamiany jako **jednostka przejściowa** przez
`systemd-run` — poza piaskownicą usługi. Całość orkiestruje **worker** portalu (nie
proces web), bo pełny `dnf` trwa minuty — dłużej niż limit czasu żądania HTTP
gunicorna, który wcześniej zabijał operację (stąd „aktualizacja nie działała").
