# Opcje imapsync

Silnik synchronizacji (imapsync) można dostroić na dwóch poziomach:

- **Globalnie** — *Ustawienia → Opcje imapsync* (`/admin/settings/imapsync`) — stosuje się do każdej skrzynki.
- **Per skrzynka** — sekcja „Dodatkowe flagi imapsync" na stronie skrzynki — dokłada się do globalnych.

## Bezpieczeństwo: co wolno, a czego nie

Pole „dodatkowe parametry" (globalne i per-skrzynka) przyjmuje **wyłącznie flagi z listy
bezpiecznych** — takie, które nie modyfikują serwera źródłowego i nie uruchamiają kodu.
Flagi mogące skasować cokolwiek na źródle (`--delete1`, `--expunge1`, …) albo uruchomić
komendę (`--pipemess`, `--exec*`) są **odrzucane z błędem** i nie da się ich zapisać.
To druga warstwa ponad twardą gwarancją w kodzie silnika, że źródło jest tylko-do-odczytu.

Dozwolone są m.in.: `--exclude`, `--include`, `--folder`, `--maxsize`, `--minsize`,
`--maxage`, `--minage`, `--addheader`, `--useheader`, `--regexmess`, `--timeout`,
`--allowsizemismatch`, `--nofoldersizes`, `--sslargs1`, `--subscribe`/`--nosubscribe`,
`--skipcrossduplicates`, `--useuid`.

## Najprzydatniejsze opcje globalne

- **Weryfikuj certyfikat SSL źródła** — domyślnie **włączona**. Chroni przed MITM. Jeśli
  serwer źródłowy ma certyfikat self-signed lub niepasujący do nazwy, synchronizacja
  padnie na etapie TLS — wtedy wyłącz tę opcję (globalnie albo dla konkretnej skrzynki
  przez `--sslargs1 SSL_verify_mode=0` w polu custom).
- **Dodawaj brakujące nagłówki** (`--addheader`) — ratunek dla wiadomości z zepsutymi/
  niekompletnymi nagłówkami na źródle (imapsync nie potrafiłby ich inaczej dopasować).
- **Maks. rozmiar** (`--maxsize`) — pomiń bardzo duże wiadomości/załączniki.
- **Timeout** — dla wolnych serwerów źródłowych.
- **Dopuszczaj niezgodność rozmiaru** (`--allowsizemismatch`) — przydatne, gdy źródło
  i cel liczą rozmiary trochę inaczej (częste między różnymi implementacjami IMAP).

## Przykłady per skrzynka

- Pomiń folder Spam i Kosz: `--exclude "^(Spam|Trash|Kosz)$"`
- Tylko wybrany folder: `--folder "INBOX"`
- Wyłącz weryfikację SSL tylko dla tej skrzynki: `--sslargs1 SSL_verify_mode=0`
