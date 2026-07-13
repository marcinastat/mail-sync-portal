# Pierwsze kroki

Portal Poczty składa się z dwóch części:

- **Roundcube** (`/`) — webmail do przeglądania i wysyłania poczty ze zsynchronizowanych skrzynek.
- **Panel administracyjny** (`/admin`) — miejsce, gdzie zarządzasz importem skrzynek, synchronizacją, użytkownikami i ustawieniami. Właśnie w nim czytasz tę stronę.

## Typowy przepływ pracy

1. **Zaimportuj skrzynki** — [Import XLS](/admin/docs/user/importing-mailboxes) — wgraj zaszyfrowane archiwum z plikiem XLS zawierającym loginy/hasła do skrzynek źródłowych.
2. **Przejrzyj i zatwierdź** — system pokaże które skrzynki są nowe, które to duplikaty, a które to aktualizacje istniejących danych. Ty decydujesz, co faktycznie zaimportować.
3. **Poczekaj na provisioning** — nowe skrzynki są automatycznie zakładane na serwerze poczty (VM2) w tle.
4. **Skonfiguruj synchronizację** — na liście [Skrzynek](/admin/mailboxes) możesz zaznaczyć wiele skrzynek naraz i ustawić: ile dni wstecz synchronizować, czy zachowywać strukturę folderów, czy kasować na docelowym gdy wiadomość zniknie ze źródła (domyślnie: nie).
5. **Monitoruj** — [Pulpit](/admin/) pokazuje ogólny stan środowiska; każda skrzynka ma własną historię synchronizacji z surowymi logami.

## Ważna zasada

Synchronizacja jest **zawsze jednokierunkowa i nigdy nie modyfikuje ani nie kasuje niczego na serwerze źródłowym** — to jest twarde ograniczenie wbudowane w kod (`portal_app/services/imapsync_runner.py`), nie tylko ustawienie, które można przypadkiem zmienić.
