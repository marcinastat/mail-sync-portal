# Strefy dostępu sieci

W **Ustawienia → Strefy dostępu sieci** (`/admin/settings/network`) można ograniczyć,
z jakich sieci osiągalny jest **panel administracyjny** i **webmail Roundcube** —
niezależnie od siebie.

## Jak to działa

Obie usługi (panel `/admin` i Roundcube `/`) dzielą ten sam port 443, więc rozróżnia
je nie zapora, lecz **nginx** — regułami `allow`/`deny` osobno dla każdej ścieżki.
To **druga warstwa** ochrony ponad zaporą firewalld (która i tak wpuszcza tylko
skonfigurowaną podsieć administracyjną).

Podajesz adresy lub sieci w notacji **CIDR**, po jednym na linię lub po przecinku:

```
192.168.88.0/24
10.8.0.5
10.9.0.0/24
```

- **Puste pole = brak dodatkowego ograniczenia** (obowiązuje wtedy tylko firewalld).
- Wpisy są walidowane — błędny CIDR nie zostanie zapisany.
- Po zapisaniu nginx jest testowany (`nginx -t`) i przeładowywany; jeśli konfiguracja
  byłaby błędna, poprzednia wersja jest **automatycznie przywracana** (literówka nie
  zostawi serwera bez WWW).

## Uwaga: nie odetnij sobie dostępu

Jeśli w polu panelu wpiszesz sieć, która **nie** obejmuje Twojego obecnego adresu,
stracisz dostęp do `/admin` (zobaczysz stronę 403). Walidacja składni i test `nginx -t`
nie chronią przed poprawną-składniowo, ale zbyt wąską listą.

W razie zablokowania: zaloguj się po SSH na VM1 i wyczyść regułę, po czym przeładuj nginx:

```
: > /etc/portal/nginx/admin-access.conf
systemctl reload nginx
```

(Pusty plik = brak ograniczenia.) To samo dla webmaila: `/etc/portal/nginx/webmail-access.conf`.
