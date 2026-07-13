# Import skrzynek z XLS/CSV

Nie masz jeszcze pliku albo chcesz dodać tylko jedną skrzynkę? Użyj
[dodawania ręcznego](/admin/mailboxes/new) — pomija cały poniższy proces i
zakłada skrzynkę od razu.

## Przygotowanie pliku

Obsługiwane formaty: **XLSX, XLS lub CSV** (dokładnie jeden arkusz/plik w
archiwum). Gotowe szablony do pobrania na `/admin/imports` (przyciski
"Pobierz szablon XLSX/CSV").

Plik musi zawierać kolumny (nazwy nagłówków rozpoznawane w wariantach PL/EN,
niewrażliwie na wielkość liter):

| Kolumna | Wymagana | Opis |
|---|---|---|
| domena źródłowa (`source_domain` / `domena`) | tak | domena skrzynki na serwerze źródłowym |
| login (`source_username` / `login` / `email`) | tak | login/adres do logowania na serwer źródłowy |
| hasło (`source_password` / `hasło`) | tak | hasło do serwera źródłowego |
| login docelowy (`destination_username`) | nie | jeśli inny niż login źródłowy; domyślnie część loginu przed `@` |
| nazwa (`display_name`) | nie | tylko informacyjnie |

Plik należy spakować do **ZIP lub 7z zabezpieczonego hasłem** (RAR działa tylko jeśli administrator zainstalował na serwerze `unrar`).

CSV: separator (przecinek, średnik lub tabulator) jest wykrywany automatycznie — typowy eksport z Excela z `;` działa bez dodatkowej konfiguracji. Zalecane kodowanie: UTF-8 (z lub bez BOM).

## Wgrywanie

1. `/admin/imports` → wybierz archiwum i podaj jego hasło.
2. System rozpakowuje plik w pamięci (tmpfs), nigdy nie zapisuje niezaszyfrowanej zawartości na trwały dysk, i analizuje wiersze.
3. Każdy wiersz dostaje etykietę:
   - **nowa** — skrzynka jeszcze nie istnieje, zostanie utworzona.
   - **duplikat w pliku** — ten sam login/domena występuje wielokrotnie w tym samym pliku; pierwsze wystąpienie wygrywa, reszta jest pomijana automatycznie.
   - **bez zmian** — skrzynka i hasło identyczne z tym, co już jest w systemie.
   - **aktualizacja** — skrzynka istnieje, ale np. hasło się zmieniło.
4. Na ekranie przeglądu odznacz wiersze, których nie chcesz importować, i zatwierdź.

## Co dzieje się po zatwierdzeniu

- Dla każdej nowej/zmienionej skrzynki system automatycznie zakłada konto na serwerze poczty (VM2), jeśli jeszcze nie istnieje.
- Domyślna polityka synchronizacji: 1 rok wstecz, pełna struktura folderów, **bez kasowania na docelowym** — możesz to zmienić per skrzynka lub grupowo na `/admin/mailboxes`.
- Hasło na skrzynce docelowej jest **lustrzaną kopią** hasła źródłowego (chyba że wcześniej ręcznie zresetowane — patrz `/admin/mailboxes/<id>`).
