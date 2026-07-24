# Otwórz skrzynkę w Roundcube z panelu (bez hasła)

Na stronie skrzynki (**Skrzynki → wybierz skrzynkę**) jest przycisk
**„✉ Otwórz w Roundcube"**. Otwiera on tę skrzynkę w webmailu **od razu
zalogowaną**, bez podawania hasła użytkownika — to dostęp administracyjny do
wglądu w pocztę zsynchronizowaną na VM2.

## Jak to działa (i dlaczego jest bezpieczne)

To jest **impersonacja** — admin ogląda cudzą skrzynkę. Dlatego jest obwarowana
kilkoma warstwami:

1. **Tylko admin z sieci admina.** Przycisk działa pod `/admin`, więc wyzwolić go
   może wyłącznie zalogowany administrator (z TOTP) z sieci dozwolonej dla panelu.
2. **Jednorazowy, krótkożyjący token.** Kliknięcie tworzy token ważny ~60 sekund,
   jednorazowy (drugie użycie jest odrzucane). W bazie trzymany jest tylko jego
   *hash*, nigdy hasło.
3. **Kontrola IP w webmailu.** Samo zalogowanie dzieje się w Roundcube (pod `/`),
   więc dodatkowo wtyczka sprawdza IP klienta wobec **tej samej listy sieci co
   strefa admina** — otwarcie zadziała tylko z sieci administracyjnej.
4. **Master user Dovecota.** Logowanie odbywa się przez konto „master" serwera
   poczty (`<skrzynka>*portaladmin`) — admin nigdy nie potrzebuje hasła skrzynki.
   Hasło mastera jest sekretem trzymanym poza repo (systemd-secrets / pliki
   root-only), a konto master nie ma własnej skrzynki.
5. **Pełny audyt.** Każde otwarcie jest zapisywane w audycie jako
   `mailbox.opened_in_roundcube` (kto, którą skrzynkę, kiedy, z jakiego IP).

## Uwagi

- W nagłówku Roundcube widać, że sesja jest „na" danej skrzynce — to sesja
  **Twojej przeglądarki**, nie użytkownika; użytkownik nic o niej nie wie i nie
  widzi jej u siebie.
- Wysyłanie poczty z tej sesji jest technicznie możliwe (SMTP też przez master),
  ale funkcja jest pomyślana do **wglądu** — traktuj ją jak podgląd archiwum.
- Jeśli skonfigurujesz [strefy dostępu sieci](network-access-zones.md), pamiętaj,
  że sieć admina musi mieć dostęp również do webmaila (`/`), inaczej samo
  przekierowanie do Roundcube zostanie zablokowane.
