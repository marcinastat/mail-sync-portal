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

## Gdzie widać wyniki

- **Pulpit panelu** — kafelek „Serwer poczty (VM2)" pokazuje sekcję **Skan
  poczty**: liczbę wykryć oraz ostatnie pozycje (skrzynka, silnik, sygnatura),
  z podziałem na `phishing`/`malware`.
- **Alerty** — worker `environment-check` przy każdym cyklu pobiera nowe wykrycia
  z VM2 i wysyła alert **`av_threat_found`** („wykryto N podejrzanych
  wiadomości"). Żeby dostawać je mailem/webhookiem, dodaj kanał w
  **Ustawienia → Kanały alertów** i zasubskrybuj zdarzenie `av_threat_found`.
  Kursor zapobiega powtarzaniu alertu o tym samym wykryciu.

Wykrycia są zapisywane na VM2 w `/var/lib/vm2-scan/findings.jsonl` (po jednym
JSON-ie na linię: czas, silnik, skrzynka, ścieżka, sygnatura, waga).

## Opcjonalnie (na przyszłość)

- **SaneSecurity** — darmowe, dodatkowe bazy sygnatur ClamAV pod zagrożenia
  mailowe (phishing/scam/złośliwe dokumenty). Podnoszą wykrywalność bez nowego
  demona; wymagają skonfigurowania `clamav-unofficial-sigs`. Nie włączone
  domyślnie (rspamd pokrywa analizę phishingu/linków).
- `clamav-milter` jest **wyłączony** (poczta wchodzi przez imapsync, nie SMTP —
  milter nic by nie skanował). Włączyć tylko, gdyby doszła realna ścieżka SMTP.
