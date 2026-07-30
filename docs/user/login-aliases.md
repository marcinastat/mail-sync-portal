# Aliasy domen logowania

Czasem skrzynki są pod jedną domeną (np. `user@example.com`), ale użytkownicy
logują się historycznie inną nazwą domeny (np. `user@example.net`) — bo tak było
ustawione na serwerze źródłowym. **Alias logowania** sprawia, że **oba adresy
działają** i wskazują **tę samą skrzynkę** (ta sama poczta, to samo hasło).

## Jak to działa

- Skrzynka fizycznie istnieje pod domeną **kanoniczną** (docelową na VM2), np.
  `user@example.com` — tam leży poczta.
- Alias to **dodatkowa nazwa domeny logowania**, np. `example.net`. Po dodaniu
  aliasu login `user@example.net` uwierzytelnia się i trafia do skrzynki
  `user@example.com` (Dovecot normalizuje tożsamość do kanonicznej, a katalog
  poczty liczy z domeny kanonicznej — więc oba loginy widzą to samo).
- **Jeden alias pokrywa wszystkie skrzynki domeny** naraz.
- To alias **logowania** (IMAP/webmail). Odbiór poczty SMTP na adres aliasu nie
  jest tym objęty (przy archiwum niepotrzebny — poczta trafia przez synchronizację).

## Dodawanie / usuwanie w panelu

1. Wejdź w **Domeny** (`/admin/domains`).
2. W karcie domeny, w sekcji **„Aliasy logowania"**, wpisz nazwę domeny aliasu
   (np. `example.net`) i kliknij **Dodaj alias**. Portal od razu wypycha alias na
   serwer poczty (VM2).
3. Aby usunąć — kliknij **usuń** przy aliasie (po potwierdzeniu). Login przez ten
   alias przestanie działać; loginy przez domenę kanoniczną działają dalej.

Każda operacja jest zapisywana w dzienniku audytu (`domain.alias.add` /
`domain.alias.remove`).

## Logowanie do Roundcube

Po dodaniu aliasu do webmaila zalogujesz się **pełnym adresem** w dowolnej z
domen — `user@example.com` **lub** `user@example.net` — tym samym hasłem skrzynki.
Zawsze podawaj pełny adres (z domeną), nie samo `user`.
