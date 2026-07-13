# Import skrzynek z XLS

## Przygotowanie pliku

Plik XLS/XLSX musi zawierać kolumny (nazwy nagłówków rozpoznawane w wariantach PL/EN):

| Kolumna | Wymagana | Opis |
|---|---|---|
| domena źródłowa (`source_domain` / `domena`) | tak | domena skrzynki na serwerze źródłowym |
| login (`source_username` / `login` / `email`) | tak | login/adres do logowania na serwer źródłowy |
| hasło (`source_password` / `hasło`) | tak | hasło do serwera źródłowego |
| login docelowy (`destination_username`) | nie | jeśli inny niż login źródłowy; domyślnie część loginu przed `@` |
| nazwa (`display_name`) | nie | tylko informacyjnie |

Plik należy spakować do **ZIP lub 7z zabezpieczonego hasłem** (RAR działa tylko jeśli administrator zainstalował na serwerze `unrar`).

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
