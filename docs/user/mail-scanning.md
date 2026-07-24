# Skanowanie poczty na VM2 (antywirus + phishing)

Zarchiwizowana poczta na VM2 jest skanowana **post factum** (nie „w locie" —
wchodzi przez imapsync, nie przez SMTP). Dwa silniki, oba FOSS:

- **ClamAV** — malware, złośliwe makra/skrypty (Office/HTML/PDF/archiwa),
  heurystyka phishingu (`PhishingScanURLs`).
- **rspamd** — analiza **phishingu i podejrzanych linków** (reputacja URL,
  RBL/SURBL), offline przez `rspamc`. Zapisujemy tylko sygnały phishingu/
  odrzucenia — nie zwykły spam (stare newslettery byłyby szumem).

## Wydajność (dlaczego już nie obciąża)

Wcześniej ClamAV re-skanował **całe 21 GB co godzinę** (~42 min/przebieg) → load ~4.
Teraz:

- **skan przyrostowy** — co godzinę skanowana jest tylko poczta **dopisana od
  ostatniego przebiegu** (sekundy zamiast 42 min),
- **pełny skan raz na dobę** (03:15) jako siatka bezpieczeństwa,
- `MaxThreads 2`, `Nice=19`, `IOSchedulingClass=idle`, `CPUQuota=150%` — skan nie
  głodzi Dovecota/Postfixa.

Ręczny pełny skan na żądanie (np. po zmianie sygnatur):
`sudo /usr/local/sbin/vm2-maildir-scan.sh full` oraz
`sudo /usr/local/sbin/vm2-rspamd-scan.sh full`.

## Dodatkowe darmowe sygnatury (SaneSecurity, URLhaus)

ClamAV używa też **darmowych sygnatur firm trzecich** przez `clamav-unofficial-sigs`
(krok `scripts/vm2/42-sanesecurity.sh`): **SaneSecurity** (phishing/scam/złośliwe
dokumenty), **URLhaus** (abuse.ch — złośliwe adresy URL), LinuxMalwareDetect,
interServer, foxhole/winnow. Mocno podnosi wykrywalność zagrożeń mailowych bez
nowego demona. Odświeżane timerem `clamav-unofficial-sigs.timer` (respektuje
cooldown mirrorów). Providerzy płatni (securiteinfo/malwarepatrol) są wyłączeni.

## Status w panelu

Pulpit → kafelek **„Serwer poczty (VM2)"** pokazuje:

- **ClamAV**: aktywny, wersja silnika, wersja bazy sygnatur, świeżość.
- **Antyspam (rspamd)**: aktywny/nieaktywny, wersja, liczba przeskanowanych,
  świeżość reguł/map.
- **Skan poczty**: liczba wykryć + ostatnie pozycje (phishing/malware).

## Wykrycia — który to mail (raporty + alerty)

- **Raporty** (`/admin/reports`) → sekcja **Wykrycia skanu poczty**: dla każdego
  wykrycia widać **którą skrzynkę** i **który mail** — temat, nadawcę i datę
  (odczytane i zdekodowane w momencie wykrycia), silnik oraz sygnaturę.
- **Alerty** — worker `environment-check` pobiera nowe wykrycia i wysyła
  **`av_threat_found`** („wykryto N podejrzanych wiadomości", z listą skrzynek/
  tematów). Żeby dostawać mailem/webhookiem: **Ustawienia → Kanały alertów**,
  zasubskrybuj `av_threat_found`. Kursor zapobiega powtarzaniu alertu o tym samym.

Wykrycia zapisywane na VM2 w `/var/lib/vm2-scan/findings.jsonl` (czas, silnik,
skrzynka, ścieżka, sygnatura, waga, temat/od/data).

> `clamav-milter` jest **wyłączony** (poczta wchodzi przez imapsync, nie SMTP —
> milter nic by nie skanował). Włączyć tylko, gdyby doszła realna ścieżka SMTP.
